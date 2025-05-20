# Wavetracker

[![Published Paper](https://img.shields.io/badge/Published%20in-Frontiers%20in%20Integrative%20Neuroscience-blue?style=for-the-badge)](https://www.frontiersin.org/articles/10.3389/fnint.2022.965211/full)

A collection of algorithms for analyzing electrode-array recordings of
wave-type electric fish. These algorithms detect individual fish, track their
signals over time, and perform post-processing to eliminate and correct
tracking errors. For a detailed explanation and usage, see the
[paper](https://www.frontiersin.org/articles/10.3389/fnint.2022.965211/full).

**Terminology Note**:  
- *Wave-type electric fish* produce continuous, quasi-sinusoidal electric organ discharges (EODs).  
- *EOD frequency* refers to the fundamental frequency of the fish’s electric organ discharge.

---

## `wavetracker`

`wavetracker` is a command-line script that tracks signals of wave-type electric fish over time by utilizing two primary features:
1. **EOD frequency (fundamentals)**  
2. **Signal strength across multiple electrodes (signatures)**

### Installation

> **Prereqs**  
> * Python 3.9 – 3.12 on your PATH  
> * Git ≥ 2.20  
> * *(Recommended)* A virtual environment manager (`venv`, Conda, Poetry, etc.)

---

#### macOS / Linux

1. Clone the dev branch

```bash
git clone -b dev https://github.com/weygoldt/wavetracker.git
cd wavetracker
```

2. (Recommended) create & activate a virtual environment

```bash
python -m venv wavetracker_env
source wavetracker_env/bin/activate
```

3. Install wavetracker in editable mode

```bash
pip install -e .
```

4. Test the installation

```bash
python -c "import importlib.metadata, wavetracker; print('wavetracker version:', importlib.metadata.version('wavetracker'))"
```

---

#### Windows

> **Good terminals to use:** PowerShell 5+, Windows Terminal, Git Bash, or the Anaconda Prompt.

```powershell
# 1 . Clone the dev branch
git clone -b dev https://github.com/weygoldt/wavetracker.git
cd wavetracker
```

**2 A. Use the built‑in `venv`**

```powershell
python -m venv wavetracker_env          # create env
.\wavetracker_env\Scripts\Activate.ps1  # PowerShell
REM —or for CMD—
REM wavetracker_env\Scripts\activate.bat

pip install -e .                        # editable install
```

**2 B. Use Conda (Anaconda / Miniconda)**

```powershell
conda create -n wavetracker python=3.11     # pick your Python
conda activate wavetracker
pip install -e .                            # still use pip here
```

**3. Verify**

```powershell
python -c "import importlib.metadata, wavetracker; print('wavetracker version:', importlib.metadata.version('wavetracker'))"
```

---

**Common gotchas on Windows**

| Symptom | Fix |
|---------|-----|
| **`Activate.ps1 cannot be loaded because running scripts is disabled…`** | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once, then re‑activate. |
| Long‑path errors on older Windows releases | Enable *Developer Mode* in *Settings → For developers* **or** `git config --system core.longpaths true`. |
| Want GPU builds of PyTorch/CUDA deps | Create the Conda env first (`conda create -n wavetracker pytorch cudatoolkit=12.1 -c pytorch -c nvidia`), then `pip install -e .`. |


### Basic Usage

To run the `wavetracker` pipeline, use the following command:

```bash
wavetracker /path/to/dataset
```

### Pipeline Overview
1. **Convert raw data to a spectrogram**.  
   The raw recordings are transformed into a time–frequency representation.  
2. **Detect harmonic groups** using the [`thunderfish`](https://github.com/bendalab/thunderfish) package.  
   This step locates harmonic structures in the spectrogram that are indicative of individual fish signals.  
3. **Track EODs** by following the fundamental frequencies of each harmonic group, assigning identities to single fish over time.

All output data from this process is stored in a single folder as `.npy` files.

---

## `cleanup`

`cleanup` is a command-line script for post-processing and refining the results produced by `wavetracker`. It discards false detections and corrects obvious tracking errors.

### Basic Usage
```bash
cleanup /path/to/wavetracker/output/folder
```

---

## EODsorter

`EODsorter` is a graphical interface for manually inspecting and correcting any remaining tracking errors. It allows for fine-grained, human supervision to ensure the tracked signals are accurate.

### Basic Usage
```bash
EODsorter /path/to/wavetracker/output/folder
```

---

## Examples

Below are two brief examples demonstrating how to use the output produced by the `wavetracker` pipeline.

### 1. Display Tracked EOD Frequency Traces

```python
import matplotlib.pyplot as plt
import numpy as np

# Load tracking results
fund_v = np.load('fund_v.npy', allow_pickle=True)   # fundamental frequencies
idx_v = np.load('idx_v.npy', allow_pickle=True)     # indices in time array
ident_v = np.load('ident_v.npy', allow_pickle=True) # fish identities
times = np.load('times.npy', allow_pickle=True)     # corresponding time points

# Extract unique fish IDs (filter out NaNs)
ids = np.unique(ident_v[~np.isnan(ident_v)])

fig, ax = plt.subplots()
for fish_id in ids:
    # Plot EOD frequency over time for each fish
    t = times[idx_v[ident_v == fish_id]]
    f = fund_v[ident_v == fish_id]
    ax.plot(t, f, marker='.', label=f'Fish {int(fish_id)}')

ax.set_xlabel('Time [s]')
ax.set_ylabel('Frequency [Hz]')
ax.legend()
plt.show()
```

**What this does**:  
- Loads the fundamental frequencies (`fund_v`), the time indices (`idx_v`), and each sample’s fish identity (`ident_v`).  
- Finds all unique fish IDs and plots the tracked frequency (y-axis) against time (x-axis) for each fish.

---

### 2. Load and Display a Fine Spectrogram

```python
import numpy as np
import matplotlib.pyplot as plt
from thunderlab.powerspectrum import decibel

# Load data
fine_freqs = np.load('fine_freqs.npy', allow_pickle=True)
fine_times = np.load('fine_times.npy', allow_pickle=True)
fine_spec_shape = np.load('fine_spec_shape.npy', allow_pickle=True)
fine_spec = np.memmap('fine_spec.npy', dtype='float', mode='r', shape=(fine_spec_shape[0], fine_spec_shape[1]), order="F")

# Set frequency and time limits for visualization
f0, f1 = 0, 1200   # frequency range [Hz]
t0, t1 = 0, 60 * 20  # time range [s] (20 minutes)

# Create frequency and time masks to slice the spectrogram
f_mask = np.arange(len(fine_freqs))[(fine_freqs >= f0) & (fine_freqs <= f1)]
t_mask = np.arange(len(fine_times))[(fine_times >= t0) & (fine_times <= t1)]

# Prepare the subset of the spectrogram for plotting and decibel transform
time_subset = fine_times[t_mask]
freq_subset = fine_freqs[f_mask]
spec_subset = decibel(fine_spec[f_mask[0]:f_mask[-1], t_mask[0]:t_mask[-1]])

# Plot the spectrogram
fig, ax = plt.subplots()
im = ax.pcolormesh(
    time_subset,
    freq_subset,
    spec_subset,
    cmap='viridis',
)

ax.set_xlabel('Time [s]')
ax.set_ylabel('Frequency [Hz]')
ax.set_title('Fine Spectrogram (dB)')
plt.colorbar(im, ax=ax, label='Power [dB]')
plt.show()
```

**What this does**:  
- Loads a higher-resolution spectrogram (`fine_spec`) along with its corresponding frequency and time axes.  
- Applies a decibel transform using `thunderlab.powerspectrum.decibel` for clearer visualization of power magnitudes.  
- Restricts the display to a specific frequency (`[f0, f1]`) and time range (`[t0, t1]`).  
- Uses `imshow` to display the spectrogram in a two-dimensional color-coded grid.

---

## Additional Notes

1. **Input Format**:  

  The `wavetracker` script expects your data to be organized into
  date/time-stamped folders, each containing one or more recordings in `.wav`
  format (or another supported audio format). An example directory structure is
  shown below:

  ```bash
  dataset/
  ├── 2024-01-01-12_34/
  │   └── recordings/
  │       ├── 2024-01-01-12_34.wav
  │       ├── 2024-01-01-12_35.wav
  │       ├── 2024-01-01-12_36.wav
  │       └── ...
  └── ...
  ```

  - **`dataset/`**  
    Top-level folder where each recording session is stored in a subfolder.
    
  - **`2024-01-01-12_34/`**  
    Example subfolder named by date and time. This helps identify individual recording sessions.
    
  - **`recordings/`**  
    Subfolder containing the actual audio files for a session. Each file typically represents a segment of continuous recording.  

    Make sure each subfolder follows this structure so that `wavetracker` can correctly locate and process your recordings.


2. **Memory Considerations**:  

   If your recordings are large, be aware that generating spectrograms and memmap files can be memory-intensive. Adjust parameters (e.g., window size, overlap) to optimize performance.

3. **Manual Inspection**:  

   Automated tracking can still yield false detections or missed events, which is why the `cleanup` and especially the `EODsorter` steps are important for achieving high-quality results.

---

**Questions or Issues?**  

If you run into problems, feel free to open an issue on [GitHub](https://github.com/weygoldt/wavetracker). Pull requests and contributions are welcome!

---

*Happy tracking!*
