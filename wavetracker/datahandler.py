import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
import argparse

import matplotlib.pyplot as plt
import numpy as np
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import torch

# from .spectrogram import *
from PyQt5.QtWidgets import *
from thunderlab.dataloader import DataLoader

from .config import Configuration
from wavetracker.device_check import get_device

device = get_device()
available_GPU = False if device.type == "cpu" else True

# try:
#     import tensorflow as tf
#     from tensorflow.python.ops.numpy_ops import np_config
#
#     np_config.enable_numpy_behavior()
#     if len(tf.config.list_physical_devices("GPU")):
#         available_GPU = True
#     else:
#         available_GPU = False
# except ImportError:
#     available_GPU = False


# def multi_channel_audio_file_generator(
#     filename: str, channels: int, data_snippet_idxs: int
# ):
#     # TODO: Make this work with overlapping snippets (last and first FFT do not
#     # overlap)
#     """
#
#     Parameters
#     ----------
#         filename : str
#             Path to the file that shall be analyzed.
#         channels : int
#             Channel count of the data to be analysed.
#         data_snippet_idxs : int
#
#     """
#     with tf.io.gfile.GFile(filename, "rb") as f:
#         while True:
#             chunk = f.read(
#                 data_snippet_idxs * channels * 4
#             )  # 4 bytes per float32 value
#             if chunk:
#                 chunk = tf.io.decode_raw(
#                     chunk,
#                     tf.float32,
#                     fixed_length=data_snippet_idxs * channels * 4,
#                 )
#                 chunk = chunk.reshape([-1, channels])
#                 yield chunk
#             else:
#                 break


class MultiChannelAudioDataset(torch.utils.data.IterableDataset):
    """Iterator for loading data from a multi-channel audio file."""

    def __init__(
        self, data_loader: DataLoader, block_size: int, noverlap: int = 0
    ) -> None:
        """Initialize the iterator for loading data from a multi-channel audio.

        Parameters
        ----------
        audio_loader : aio.AudioLoader
            An instance of the AudioLoader class for loading audio data.
        block_size : int
            The size of each data block to be loaded.
        noverlap : int, optional
            Number of overlapping samples between blocks, by default 0.
        """
        self.data_loader = data_loader
        self.block_size = block_size
        self.noverlap = noverlap

    def __iter__(self):
        with self.data_loader as data:
            for block in data.blocks(self.block_size, self.noverlap):
                yield torch.from_numpy(block)


def open_raw_data(
    filename: str,
    buffersize: float = 60.0,
    backsize: float = 0.0,
    channel: int = -1,
    snippet_size: int = 2**21,
    verbose: int = 0,
    logger=None,
    **kwargs: dict,
):
    """
    Loades data from electric fish grid recordings and provides it as accessible variable. Since files are rather large,
    retured arrays are either based on a buffer (for details see thunderfish.dataloader) or are yielded from a
    generator (GPU pathway using tensorflow).

    Parameters
    ----------
        filename : str
            Path to the file that shall be analyzed.
        buffersize : float
            Size of internal buffer in seconds.
        backsize : float
            Part of the buffer to be loaded before the requested start index in seconds.
        channel : int
            The single channel to be worked on or all channels if negative.
        snippet_size : int
            Sample count that is contained in one data snippet handled by the respective spectogram functions at once.
        verbose : int
            Verbosity level regulating shell/logging feedback during analysis. Suggested for debugging in development.
        logger : object
            If not None, logger object that stores feedback about processing status
        kwargs : dict
             Excess parameters from the configuration dictionary passed to the function.

    Returns
    -------
        data : 2d-array
            Contains the raw-data from electrode (grid) recordings of electric fish. Data shape resembles samples
            (1st dimension) x channels (2nd dimension).
        samplerate : float
            Samplerate of the data that shall be analyzed.
        channels : int
            Channel count of the data to be analysed.
        dataset : 2d-tensor
            Contains the same values as data, but is presented as data from generator, that is efficiently used by
            tensorflow in the current GPU analysis pipeline.
        shape : tuple
            Shape of data.

    """

    if isinstance(filename, str):
        folder = os.path.split(filename)[0]
    else:
        folder = os.path.split(filename[0])[0]

    # filename = os.path.join(folder, 'traces-grid1.raw')
    # print(filename)
    data = DataLoader(
        filename,
        buffersize=buffersize,
        backsize=backsize,
        # channel=channel,
    )
    samplerate = data.rate
    channels = data.channels
    shape = data.shape

    if verbose >= 1:
        logger.info(f"Loading data from: {os.path.abspath(folder)}")
    dataset = None
    if available_GPU:
        # dataset = tf.data.Dataset.from_generator(
        #     multi_channel_audio_file_generator,
        #     args=(filename, channels, snippet_size),
        #     output_types=tf.float32,
        #     output_shapes=tf.TensorShape([None, channels]),
        # )
        dataset = MultiChannelAudioDataset(
            data_loader=data, block_size=snippet_size, noverlap=0
        )
        logger.info("Torch iterator loaded")

    return data, samplerate, channels, dataset, shape


def main(args):
    # if args.verbose >= 1:
    # print("\n--- Running wavetracker.datahandler ---")

    cfg = Configuration(args.config, verbose=args.verbose)

    data, samplerate, channels, dataset, data_shape = open_raw_data(
        filename=args.file, verbose=args.verbose, **cfg.spectrogram
    )

    fig, ax = plt.subplots(
        int(np.ceil(data_shape[1] / 2)),
        2,
        figsize=(20 / 2.54, 20 / 2.54),
        sharex="all",
        sharey="all",
    )
    ax = np.hstack(ax)
    d = data[0 : cfg.spectrogram["snippet_size"], :]
    fig.suptitle("Data loaded with thunderfish.DataLoader")
    for i in range(channels):
        ax[i].plot(
            np.arange(cfg.spectrogram["snippet_size"]) / samplerate, d[:, i]
        )
        ax[i].text(
            0.9,
            0.9,
            f"{i}",
            transform=ax[i].transAxes,
            ha="center",
            va="center",
        )
    plt.show()

    if available_GPU:
        for enu, data in enumerate(dataset.take(2)):
            fig, ax = plt.subplots(
                int(np.ceil(data_shape[1] / 2)),
                2,
                figsize=(20 / 2.54, 20 / 2.54),
                sharex="all",
                sharey="all",
            )
            ax = np.hstack(ax)
            d = data.numpy()
            fig.suptitle("Data loaded with tensorflow.generator")
            for i in range(channels):
                ax[i].plot(
                    (
                        np.arange(cfg.spectrogram["snippet_size"])
                        + enu * cfg.spectrogram["snippet_size"]
                    )
                    / samplerate,
                    d[:, i],
                )
                ax[i].text(
                    0.9,
                    0.9,
                    f"{i}",
                    transform=ax[i].transAxes,
                    ha="center",
                    va="center",
                )
            plt.show()


if __name__ == "__main__":
    example_data = (
        "/data1/data/2023_Breeding/raw_data/2023-02-09-08_16/traces-grid1.raw"
    )
    parser = argparse.ArgumentParser(
        description="Evaluated electrode array recordings with multiple fish."
    )
    # parser.add_argument('-f', '--folder', type=str, help='file to be analyzed', default=example_data)
    parser.add_argument(
        "file", nargs="?", type=str, help="file to be analyzed"
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
        "-s", "--shell", action="store_true", help="execute shell pipeline"
    )
    args = parser.parse_args()
    if args.file:
        args.file = os.path.normpath(args.file)

    main(args)
