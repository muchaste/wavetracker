import argparse
import multiprocessing
import os
import sys
import time
from functools import partial
from pathlib import Path

import numpy as np
from rich.progress import Progress
from thunderfish.harmonics import fundamental_freqs, harmonic_groups

from wavetracker.config import Configuration
from wavetracker.datahandler import open_raw_data, MultiChannelAudioDataset
from wavetracker.device_check import get_device
from wavetracker.gpu_harmonic_group import (
    get_fundamentals,
    harmonic_group_pipeline,
)
from wavetracker.logger import get_logger
from wavetracker.spectrogram import (
    Spectrogram,
    compute_aligned_snippet_length,
    get_step_and_overlap,
)
from wavetracker.tracking import freq_tracking_v6

log = get_logger(__name__)

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# Custom progress bar
pbar = Progress(
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    BarColumn(),
    MofNCompleteColumn(),
    TextColumn("•"),
    TimeElapsedColumn(),
    TextColumn("•"),
    TimeRemainingColumn(),
)

device = get_device()
available_GPU = False if device.type == "cpu" else True

# warnings.filterwarnings("ignore")
# os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
# try:
#     import tensorflow as tf
#     from tensorflow.python.ops.numpy_ops import np_config
#
#     np_config.enable_numpy_behavior()
#     if len(tf.config.list_physical_devices("GPU")):
#         available_GPU = True
#         msg = "Tensorflow installed, running on GPU."
#         log.info(msg)
#     else:
#         available_GPU = False
#         msg = "Tensorflow installed, but no GPU available. Defaulting to CPU analysis."
#         log.warning(msg)
# except ImportError:
#     available_GPU = False
#     msg = "Tensorflow not installed, defaulting to CPU analysis."
#     log.info(msg)


class AnalysisPipeline:
    """
    Main analysis pipeline of wavetracker-package to analyse electric grid recordings of wave-type electric fish by
    means of extracting individual EOD frequencies from spectrograms and tracking them based on frequency and spatial
    electric field property similarities (Raab et al., 2022).

    """

    def __init__(
        self,
        data,
        samplerate,
        channels,
        dataset,
        data_shape,
        cfg,
        folder,
        save_path,
        verbose,
        spec,
        logger=None,
        gpu_use=False,
    ):
        """
        Constructs all the necessary attributes for the main analysis pipeline of the wavetracker-package to analyse
        electric grid recordings of wave-type electric fish. After initializing config-parameters, the data to analise is
        loaded, a Spectrogram-class is initialized and potentially pre-analyzed datafiles are loaded if available.

        Parameters
        ----------
            data : 2d-array
                Contains the raw-data from electrode (grid) recordings of electric fish. Data shape resembles samples
                (1st dimension) x channels (2nd dimension).
            samplerate : int
                Samplerate of the data store in data.
            channels : int
                Channel count of the data to be analysed.
            dataset :
                Contains the same values as data, but is presented as data from generator, that is efficiently used by
                tensorflow in the current GPU analysis pipeline.
            data_shape : tuple
                Shape of data.
            cfg : object
                Multiple dictionaries containing config parameters for each analysis step, e.g. spectrogram, harmonic groups, or tracking.
            folder : str
                Folder where raw-data is stored.
            verbose : int
                Verbosity level regulating shell/logging feedback during analysis. Suggested for debugging in development.
            logger : object, optional
                Logger object used to store analysis feedback (default in None).
            gpu_use : bool, optional
                If True uses the way faster GPU analysis pipeline (default in False).
        """
        self.save_path = save_path

        self.data = data
        self.samplerate = samplerate
        self.channels = channels
        self.dataset = dataset
        self.data_shape = data_shape
        self.cfg = cfg
        self.folder = folder

        self.verbose = verbose
        self.logger = logger
        self.gpu_use = gpu_use
        self.core_count = multiprocessing.cpu_count()

        self.Spec = spec
        # self.Spec = Spectrogram(
        #     self.samplerate,
        #     self.data_shape,
        #     folder=self.folder,
        #     verbose=verbose,
        #     gpu_use=gpu_use,
        #     **cfg.raw,
        #     **cfg.spectrogram,
        # )

        self._get_signals = True
        self.do_tracking = True

        # load
        if os.path.exists(os.path.join(self.save_path, "fund_v.npy")):
            msg = "Loading pre-analyzed data."
            log.info(msg)
            self._fund_v = np.load(
                os.path.join(self.save_path, "fund_v.npy"), allow_pickle=True
            )
            self._idx_v = np.load(
                os.path.join(self.save_path, "idx_v.npy"), allow_pickle=True
            )
            self._sign_v = np.load(
                os.path.join(self.save_path, "sign_v.npy"), allow_pickle=True
            )
            self.ident_v = np.load(
                os.path.join(self.save_path, "ident_v.npy"), allow_pickle=True
            )
            self.times = np.load(
                os.path.join(self.save_path, "times.npy"), allow_pickle=True
            )
            self.get_signals = False
            if len(self.ident_v[~np.isnan(self.ident_v)]) > 0:
                self.do_tracking = False
        else:
            msg = "No pre-analyzed data found."
            log.info(msg)
            self._fund_v = []
            self._idx_v = []
            self._sign_v = []
            self.ident_v = []
            self.times = []

        msg = "Analysis pipeline initialized."
        log.info(msg)

    @property
    def get_signals(self):
        """
        Get signals represents the task of extracting EOD signals from Spectrogram analysis step. If this is False
        subsequent analysis steps depend on loaded signals.
        """
        return bool(self._get_signals)

    @get_signals.setter
    def get_signals(self, get_sigs):
        """
        Sets the task to extract EOD signals from Spectrogram analysis step. Associated parameters are purged while
        setting.
        """
        if get_sigs:
            self._fund_v = []
            self._idx_v = []
            self._sign_v = []
            self.ident_v = []
            self.times = []
        self._get_signals = bool(get_sigs)

    @property
    def fund_v(self):
        """
        Assures this vector to be extracted from the class as numpy.array.
        """
        return np.array(self._fund_v)

    @property
    def idx_v(self):
        """
        Assures this vector to be extracted from the class as numpy.array.
        """
        return np.array(self._idx_v)

    @property
    def sign_v(self):
        """
        Assures this vector to be extracted from the class as numpy.array.
        """
        return np.array(self._sign_v)

    def run(self):
        """
        Coordinates the procedures of the AnalysisPipeline class. This includes the output of analysis feedback in the
        shell/logger-file, the coordination of required tasks (spectrogram, signal extraction, tracking), as well as the
        determination of hardware to be used in this process.

        Different pathways for GPU assisted analysis and standard CPU analysis are available and executed depending on
        Hardware availability.
        """
        # if self.verbose >= 1:
        #     print(
        #         f'{"Spectrogram (GPU)":^25}: '
        #         f'-- fine spec: {self.Spec.get_fine_spec} '
        #         f'-- plotable spec: {self.Spec.get_sparse_spec} '
        #         f'-- signal extract: {self._get_signals} '
        #         f'-- snippet size: {self.Spec.snippet_size / self.samplerate:.2f}s'
        #     )
        self.logger.info(
            f"Spectrogram:\n"
            f"-- fine spec: {self.Spec.get_fine_spec}\n"
            f"-- plotable spec: {self.Spec.get_sparse_spec}\n"
            f"-- signal extract: {self._get_signals}\n"
            f"-- snippet size: {self.Spec.snippet_size / self.samplerate:.2f}s\n"
        )

        self.logger.info(f"GPU use : {self.gpu_use}\n")

        if (
            self._get_signals
            or self.Spec.get_fine_spec
            or self.Spec.get_sparse_spec
        ):
            if self.gpu_use:
                self.pipeline_GPU()
            else:
                self.pipeline_CPU()
            self.times = self.Spec.times
            self.save()

        if self.verbose >= 1:
            self.logger.info(
                f"Tracking:\n"
                f"-- freq_tolerance: {self.cfg.tracking['freq_tolerance']}\n"
                f"-- max_dt: {self.cfg.tracking['max_dt']}\n"
            )
        if self.do_tracking:
            self.ident_v = freq_tracking_v6(
                self.fund_v,
                self.idx_v,
                self.sign_v,
                self.times,
                verbose=self.verbose,
                **self.cfg.harmonic_groups,
                **self.cfg.tracking,
            )
            self.save()

    def pipeline_GPU(self):
        """
        Executes the analysis pipeline comprising spectrogram analysis and signal extracting using GPU.
        """
        iterations = int(np.floor(self.data_shape[0] / self.Spec.snippet_size))

        iter_counter = 0

        with pbar:
            task = pbar.add_task(
                "Spectrogram + Harmonic Group", total=iterations
            )
            for enu, snippet_data in enumerate(self.dataset):
                t0_snip = time.time()
                snippet_t0 = (
                    self.Spec.itter_count
                    * self.Spec.snippet_size
                    / self.samplerate
                ) + self.Spec.snippet_overlap // 2 * self.samplerate

                if (
                    self.data.shape[0] // self.Spec.snippet_size
                    == self.Spec.itter_count
                ):
                    self.Spec.terminate = True

                t0_spec = time.time()
                self.Spec.snippet_spectrogram(
                    snippet_data.T, snipptet_t0=snippet_t0
                )
                t1_spec = time.time()

                t0_hg = time.time()
                if self._get_signals:
                    self.extract_snippet_signals()
                t1_hg = time.time()

                iter_counter += 1
                t1_snip = time.time()
                if self.verbose == 3:
                    self.logger.info(
                        f"Progress {iter_counter / iterations:3.1%}\n"
                        f"-- Spectrogram: {t1_spec - t0_spec:.2f}s\n"
                        f"-- Harmonic group: {t1_hg - t0_hg:.2f}s\n"
                        f"--> {t1_snip-t0_snip:.2f}s\n",
                    )
                pbar.update(task, advance=1)
                if enu == iterations - 1:
                    break

    def pipeline_CPU(self):
        """
        Executes the analysis pipeline comprising spectrogram analysis and signal extracting using CPU only.
        """
        counter = 0
        iterations = self.data.shape[0] // (
            self.Spec.snippet_size - self.Spec.noverlap
        )

        with pbar:
            task = pbar.add_task("File analysis.", total=iterations)
            for i0 in np.arange(
                0,
                self.data.shape[0],
                self.Spec.snippet_size - self.Spec.noverlap,
            ):
                t0_snip = time.time()
                snippet_t0 = i0 / self.samplerate

                if (
                    self.data.shape[0]
                    // (self.Spec.snippet_size - self.Spec.noverlap)
                    * (self.Spec.snippet_size - self.Spec.noverlap)
                    == i0
                ):
                    self.Spec.terminate = True

                t0_spec = time.time()
                snippet_data = [
                    self.data[i0 : i0 + self.Spec.snippet_size, channel]
                    for channel in self.Spec.channel_list
                ]
                self.Spec.snippet_spectrogram(
                    snippet_data, snipptet_t0=snippet_t0
                )
                t1_spec = time.time()

                t0_hg = time.time()
                self.extract_snippet_signals()
                t1_hg = time.time()
                t1_snip = time.time()
                if self.verbose == 3:
                    self.logger.info(
                        f"Progress {counter / iterations:3.1%}\n"
                        f"-- Spectrogram: {t1_spec - t0_spec:.2f}s\n"
                        f"-- Harmonic group: {t1_hg - t0_hg:.2f}s\n"
                        f"--> {t1_snip-t0_snip:.2f}s\n",
                    )
                counter += 1
                pbar.update(task, advance=1)

    def extract_snippet_signals(self):
        """
        Extracts harmonic groups from a snippet spectrogram. Different features of the extracted signals are sorted in
        the output arrays of the pipeline, i.e. their fundamental frequencies in "fund_v", the power of these frequencies
        accross recording electrodes in "sign_v", and their associated time indices in "idx_v".

        Different pathways for GPU assisted analysis and standard CPU analysis are available and executed depending on
        Hardware availability.
        """
        if self.gpu_use:
            assigned_hg, peaks, log_spec = harmonic_group_pipeline(
                self.Spec.sum_spec,
                self.Spec.spec_freqs,
                self.cfg,
                verbose=self.verbose,
            )
            tmp_fundamentals = get_fundamentals(
                assigned_hg, self.Spec.spec_freqs
            )
        else:
            partial_harmonic_groups = partial(
                harmonic_groups,
                self.Spec.spec_freqs,
                **self.cfg.harmonic_groups,
            )

            pool = multiprocessing.Pool(self.core_count - 1)
            a = pool.map(
                partial_harmonic_groups, self.Spec.sum_spec.transpose()
            )

            groups_per_time = [a[groups][0] for groups in range(len(a))]
            tmp_fundamentals = pool.map(fundamental_freqs, groups_per_time)
            pool.terminate()

        tmp_fund_v = np.hstack(tmp_fundamentals)
        tmp_idx_v = np.array(
            np.hstack(
                [
                    np.ones(len(f)) * enu
                    for enu, f in enumerate(tmp_fundamentals)
                ]
            ),
            dtype=int,
        )
        f_idx = [
            np.argmin(np.abs(self.Spec.spec_freqs - f))
            for i in range(len(tmp_fundamentals))
            for f in tmp_fundamentals[i]
        ]

        tmp_sign_v = self.Spec.spec[:, f_idx, tmp_idx_v].transpose()

        idx_0 = len(self.Spec.times) - len(self.Spec.spec_times)

        self._fund_v.extend(tmp_fund_v)
        self._idx_v.extend(tmp_idx_v + idx_0)
        self._sign_v.extend(tmp_sign_v)
        self.ident_v = np.full(len(self._idx_v), np.nan)

    def save(self):
        """
        Save analyzed data arrays.
        """
        if not os.path.exists(self.save_path):
            os.makedirs(self.save_path)

        np.save(os.path.join(self.save_path, "fund_v.npy"), self.fund_v)
        np.save(os.path.join(self.save_path, "ident_v.npy"), self.ident_v)
        np.save(os.path.join(self.save_path, "idx_v.npy"), self.idx_v)
        np.save(os.path.join(self.save_path, "times.npy"), self.times)
        np.save(os.path.join(self.save_path, "sign_v.npy"), self.sign_v)

        self.Spec.save()


def cli() -> argparse.Namespace:
    """Command line interface for wavetracker."""
    parser = argparse.ArgumentParser(
        description="Evaluated electrode array recordings with multiple fish."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Path to directory of recording or to file to be analyzed",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="<config>.yaml file for analysis",
        default=None,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbose",
        default=0,
        help="verbosity level. Increase by specifying -v multiple times, or like -vvv",
    )
    parser.add_argument(
        "--cpu", action="store_true", help="analysis using only CPU."
    )
    parser.add_argument(
        "-r",
        "--renew",
        action="store_true",
        help="redo all analysis; dismiss pre-saved files.",
    )
    parser.add_argument(
        "-l",
        "--logging",
        action="store_true",
        help="store sys.out in log.txt.",
    )
    parser.add_argument(
        "-n", "--nosave", action="store_true", help="dont save spectrograms"
    )
    args = parser.parse_args()
    return args


def main():
    args = cli()

    # STEP 0: Check if dataset is single file or directory of many .wav files
    file, folder = None, None
    if args.path.is_dir():
        file = sorted(args.path.glob("*.wav"))
        folder = args.path
        file = [str(x.absolute()) for x in file]
    else:
        file = str(args.path.absolute())
        folder = args.path.absolute().parent

    save_path = list(folder.parts)
    save_path[-3] = "intermediate"
    save_path = Path(*save_path)
    save_path.mkdir(exist_ok=True, parents=True)
    save_path = str(save_path)
    folder = str(folder)

    # STEP 1: Load wavetracker configuration
    cfg = Configuration(args.config, verbose=args.verbose, logger=log)

    # STEP 2: Load the raw data
    data, samplerate, channels, data_shape = open_raw_data(
        filename=file,
        verbose=args.verbose,
        logger=log,
        **cfg.spectrogram,
    )

    # STEP 3: Set the snippet size in accordance with the spectrogram parameters
    usable_snippet_length = int(cfg.spectrogram["snippet_size"] * samplerate)
    snippet_overlap = int(
        cfg.spectrogram["snippet_overlap_frac"] * usable_snippet_length
    )
    total_snippet_length = usable_snippet_length + snippet_overlap

    step, overlap = get_step_and_overlap(
        overlap_frac=cfg.spectrogram["overlap_frac"],
        nfft=cfg.spectrogram["nfft"],
    )

    better_snippet_size_samples = compute_aligned_snippet_length(
        total_snippet_length, step, overlap
    )

    # STEP 4: Generate the torch iterator dataset object
    # Just a better way to iterate through the dataset for spectrogram analysis
    dataset = MultiChannelAudioDataset(
        data_loader=data,
        block_size=better_snippet_size_samples,
        noverlap=snippet_overlap,  # This is NOT the noverlap of the spectrogram!
    )

    # STEP 5: Generate the Spectrogram object
    spec = Spectrogram(
        samplerate=samplerate,
        snippet_size=better_snippet_size_samples,
        snippet_overlap=snippet_overlap,
        data_shape=data_shape,
        nfft=cfg.spectrogram["nfft"],
        step=step,
        noverlap=overlap,
        channels=channels,
        verbose=args.verbose,
        folder=save_path,
        overlap_frac=cfg.spectrogram["overlap_frac"],
    )

    # STEP 6: Initialize analysis pipeline class
    analysis = AnalysisPipeline(
        data=data,
        samplerate=samplerate,
        channels=channels,
        dataset=dataset,
        data_shape=data_shape,
        cfg=cfg,
        folder=folder,
        save_path=save_path,
        verbose=args.verbose,
        logger=log,
        gpu_use=not args.cpu and available_GPU,
        spec=spec,
    )

    if args.renew:
        (
            analysis.Spec.get_sparse_spec,
            analysis.Spec.get_fine_spec,
            analysis.get_signals,
        ) = True, True, True

    if args.nosave:
        analysis.Spec.get_sparse_spec, analysis.Spec.get_fine_spec = (
            False,
            False,
        )

    # STEP 7: Run the analysis
    analysis.run()

    sys.stdout.close()


if __name__ == "__main__":
    main()
