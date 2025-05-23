import os
import sys

import ruamel.yaml


class Configuration:
    """
    Configuration class providing meta-parameters for the different processing steps in the wavetracker pipeline.
    The Object attributes refelct the differen analysis stages, e.g. "spectrogram", "harmonix_groups", and "tracking".
    """

    def __init__(
        self,
        folder: str = None,
        file: str = None,
        verbose: int = 0,
        logger=None,
    ) -> None:
        """
        Constructs all necessary parameters and attributes to generate/provide a configuration file for the
        wavetracker-package.

        Parameters
        ----------
        folder
        file
        verbose
        logger
        """
        if folder == None:
            # folder = os.path.dirname(os.path.abspath(__file__))
            folder = os.path.dirname(os.path.abspath(__file__))
        self.file = file
        self.verbose = verbose
        if not file:
            self.find_config(folder)
        else:
            self.file = file

        self.basic = {}
        self.spectrogram = {}
        self.raw = {}
        self.harmonic_groups = {}
        self.tracking = {}

        if self.verbose >= 1:
            # print(f'{"Config file from":^25}: {os.path.realpath(self.file)}.')
            # if logger:
            logger.info(f"Config file from: {os.path.realpath(self.file)}.")

        self.yaml = ruamel.yaml.YAML()
        with open(self.file) as f:
            self.cfg = self.yaml.load(f)
            self.dicts = list(self.cfg.keys())
            for dict in self.cfg:
                setattr(self, dict, self.cfg[dict])
            f.close()

    def __repr__(self) -> str:
        rep_list = []
        for dict in self.dicts:
            rep_list.append(f"{dict}:")
            rep_list.extend(
                list(
                    f"  {k: <16}:  {v}"
                    for k, v in zip(
                        getattr(self, dict).keys(),
                        getattr(self, dict).values(),
                        strict=False,
                    )
                )
            )
        return "\n".join(rep_list)

    def find_config(self, folder) -> None:
        """
        Search for a .yaml file that contains configuration data. First look in input folder, second in the data derectory,
        and last in the programm directory. In none is available, create the standard config file with standard settings
        (as define in fn "create_standard_cfg_file").

        Parameters
        ----------
            folder : str
                Folder where to search first for the .yaml file containing the configuration data.
        """
        folder = os.path.realpath(folder)
        folder = os.path.normpath(folder)
        search_folders = [
            folder,
            os.sep.join(folder.split(os.sep)[:-1]),
            os.path.dirname(os.path.abspath(__file__)),
        ]

        found = False
        for search_folder in search_folders:
            for dirpath, dirnames, filenames in os.walk(
                search_folder, topdown=True
            ):
                for filename in [f for f in filenames if f.endswith(".yaml")]:
                    self.file = os.path.join(dirpath, filename)
                    found = True
                    break
                if found:
                    break
            if found:
                break
        if not found:
            self.file = create_standard_cfg_file()

    @property
    def keys(self) -> list:
        """
        Get the Object attributes, representing the differen analysis stages in the wavetracker pipeline.
        """
        return self.dicts

    def save(self) -> None:
        """
        Translate object attributes to a dictonary which will be saved in its original loading path.
        """
        for dict in self.cfg:
            self.cfg[dict] = getattr(self, dict)
        with open(self.file, "w") as f:
            self.yaml.dump(self.cfg, f)
            f.close()


def create_standard_cfg_file(folder="."):
    """
    Create a standard configuration file, when none could be found to be loaded.

    Parameters
    ----------
        folder : str
            Folder where the generated config-file shall be saved.
    """
    yaml_str = """\
    # Basic configureation
    basic:
      project: wavetracker
      version: 0.1

    # Data processing configuration
    data_processing:
      snippet_size: 2**21
      channels: -1

    # add another comment
    spectrogram:
      snippet: 2**21
      nfft: 2**15
      overlap_frac: 0.9
    """
    yaml = ruamel.yaml.YAML()  # defaults to round-trip if no parameters given
    code = yaml.load(yaml_str)

    file = os.path.join(folder, "cfg.yaml")
    yaml.dump(code, file)
    return file


def main():
    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        folder = "."
    c = Configuration(folder)
    exit(c.save())


if __name__ == "__main__":
    main()
