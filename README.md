# Port Tuning Calculator

A desktop loudspeaker enclosure simulation tool that predicts how a driver will perform in a vented (ported) box design. Built with Python, Tkinter, and Matplotlib.

---

## What It Does

This program models a loudspeaker as a coupled electrical–mechanical–acoustical circuit and solves it across a range of frequencies. Given a set of driver parameters (Thiele-Small) and box/port dimensions, it calculates:

| Output | Description |
|---|---|
| **Impedance** | Total electrical impedance seen by the amplifier (Ohms) — shows the characteristic double-peaked curve of a vented system |
| **Cone Excursion** | Peak physical displacement of the speaker cone (mm) — useful for checking whether you'll exceed the driver's Xmax |
| **Port Velocity** | Peak air velocity through the port (m/s) — high velocities cause audible turbulence ("port noise") |
| **Group Delay** | Time-domain smearing introduced by the system (ms) — derived from the phase response of the input impedance |
| **Port Tuning (fb)** | The resonant frequency of the port/box system (Hz) — calculated from enclosure geometry using empirical formulas |

All plots include an interactive cursor that snaps to the nearest data point and displays precise readouts as you hover.

---

## The Physics

The simulation is based on the **electroacoustic equivalent circuit model** described by Janne Ahonen, the mathematician and electroacoustic engineer behind [WinISD](http://www.linearteam.dk/?pageid=winisd).

### The Three-Mesh Model

A loudspeaker in a vented box is modeled as three coupled circuits, each obeying Ohm's law in their respective domain:

**1. Electrical Circuit** — The amplifier voltage (Vg) drives current (I) through the voice coil:

```
Vg = I·(Re + s·Le) + U·Bl
```

**2. Mechanical Circuit** — The motor force (Bl·I) drives cone velocity (U) through the suspension:

```
Bl·I = U·(Rms + s·Mms + 1/(s·Cms)) + Sd·Pd
```

**3. Acoustical Circuit** — The cone's volume velocity (Sd·U) generates pressure (Pd) across the box impedance:

```
Pd = U · Sd · Zb
```

Where `s = jω` is the complex frequency variable, and `Zb` is the impedance of the vented box — three parallel branches representing the air spring (Ccab), enclosure leaks (Ral), and port air mass (Lmap):

```
1/Zb = s·Ccab + 1/Ral + 1/(s·Lmap)
```

Solving algebraically gives the input impedance and all derived quantities:

```
Zin = (Re + s·Le) + Bl² / (Zm + Sd²·Zb)
```

### Port Tuning

The port tuning frequency (fb) is calculated by averaging two well-known empirical formulas (JL Audio and DIY Audio) rather than deriving it purely from the circuit model. This approach was chosen deliberately — the average of these two formulas produces results that closely match real-world measurements across a wide range of enclosure geometries.

### Dual Voice Coil Support

For drivers with dual voice coils, the effective electrical parameters are adjusted based on wiring configuration:

| Wiring | Re | Le | Bl |
|---|---|---|---|
| Series | Re × 2 | Le × 2 | Bl × 2 |
| Parallel | Re / 2 | Le / 2 | Bl (unchanged) |

---

## Project Structure

```
Claude-Port-Tuning-Calc/
├── main.py        ← Entry point + full Tkinter GUI
├── physics.py     ← Equivalent circuit solver (pure math, no GUI code)
├── units.py       ← Unit conversion utility (dimension-safe)
├── test_data.py   ← Reference test values (Tymphany XLS-12 driver)
└── README.md
```

**Design principles:**
- `physics.py` has zero knowledge of the GUI — it takes dataclasses in and returns dataclasses out, making it independently testable and reusable.
- `units.py` is a standalone utility that groups units by physical dimension, preventing nonsensical conversions (e.g., meters → kilograms).
- `main.py` is a thin layer that collects inputs, calls the physics engine, and plots results.

---

## Getting Started

### Requirements

- **Python 3.14+**
- **NumPy** — numerical computing
- **Matplotlib** — plotting and interactive graphs

Tkinter is included with standard Python installations on most platforms.

### Installation

```bash
# Clone the repository
git clone https://github.com/DLHgn/Claude-Port-Tuning-Calc.git
cd Claude-Port-Tuning-Calc

# Install dependencies
pip install numpy matplotlib

# Run the application
python main.py
```

### Quick Start

1. Launch the app with `python main.py`
2. Click **Load Test** to populate all fields with reference values (Tymphany XLS-12 driver in a 100L vented box)
3. Click **Submit** or switch to the **Graphs** tab and click **Update Graph**
4. Use the dropdown to switch between Impedance, Cone Excursion, Port Velocity, and Group Delay views
5. Hover over the plot to see precise frequency/value readouts

---

## Test Data

The built-in test values come from the **Tymphany XLS-12** driver datasheet, which was used in Janne Ahonen's original LTSpice simulation examples. This provides a known reference point for validating results against LTSpice and WinISD.

| Parameter | Value | Unit | Description |
|---|---|---|---|
| Re | 3.5 | Ω | Voice coil DC resistance |
| Le | 4.2 | mH | Voice coil inductance |
| Bl | 17.6 | T·m | Motor force factor |
| Sd | 466.2 | cm² | Effective cone area |
| Cms | 0.46 | mm/N | Mechanical compliance |
| Mms | 166.3 | g | Total moving mass |
| Rms | 5.12 | Kg/s | Mechanical resistance |
| Vb | 100 | L | Box net volume |
| Port Area | 79 | cm² | Port cross-section |
| Port Length | 30.3 | cm | Physical port length |

---

## Acknowledgments

This project was inspired by and built upon the electroacoustic modeling work of **Janne Ahonen** (B.Sc. EE), who served as the mathematician and electroacoustic model engineer for [WinISD](https://www.linearteam.org/). His generous and detailed correspondence explaining the equivalent circuit approach, LTSpice modeling techniques, and multi-driver parameter adjustments was foundational to this project.

**References:**
- Janne Ahonen — WinISD electroacoustic model documentation and private correspondence (2021)
- W. Marshall Leach — *Introduction to Electroacoustics and Audio Amplifier Design*

---

## License

This project is provided as-is for personal and educational use. Not intended for commercial purposes.
