"""
main.py — Port Tuning Calculator GUI
======================================

This is the entry point for the application. Run it with:
    python main.py

The GUI is built with Tkinter (Python's built-in GUI toolkit) and Matplotlib
for plotting. It provides:

  - An "Inputs" tab where you enter driver Thiele-Small parameters and
    box/port dimensions, with unit selection buttons for each field.
  - A "Graphs" tab where you select what to plot (impedance, excursion,
    port velocity, or group delay) and view interactive results.

Architecture:
  - This file handles ONLY the user interface. It collects inputs from
    widgets, converts them to SI units using `units.py`, builds the
    dataclass objects defined in `physics.py`, calls the physics engine,
    and plots the results.
  - The physics engine (`physics.py`) has zero knowledge of Tkinter.
  - The unit converter (`units.py`) has zero knowledge of either.
"""

import math
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import matplotlib
matplotlib.use("TkAgg")  # Must be set before importing pyplot
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import physics
import units
import test_data


# =============================================================================
# Configuration Constants
# =============================================================================

PAD = 5                # Universal widget padding (pixels)
ENTRY_WIDTH = 10       # Character width for numeric entry fields
WINDOW_TITLE = "Port Tuning Calculator"

# End correction labels → numeric factors.
# These account for the extra air mass at the port openings, which depends
# on how the port exits are mounted relative to the enclosure walls.
END_CORRECTION_OPTIONS = [
    "One Flanged End",
    "Both Flanged Ends",
    "Both Free Ends",
    "3 Common Walls",
    "2 Common Walls",
    "1 Common Wall",
]

END_CORRECTION_MAP = {
    "One Flanged End":   0.732,
    "Both Flanged Ends": 0.850,
    "Both Free Ends":    0.614,
    "3 Common Walls":    2.227,
    "2 Common Walls":    1.728,
    "1 Common Wall":     1.230,
}


# =============================================================================
# Interactive Cursor — Snaps to the nearest data point on the plot
# =============================================================================

class SnapCursor:
    """
    Attaches to a Matplotlib line and shows an annotation that follows the
    mouse, snapping to the nearest data point on the line.

    This gives the user precise readouts (e.g., "Freq: 42.0 Hz / Imp: 28.3 Ω")
    without needing to click — just hover over the plot.
    """

    def __init__(self, ax, line, formatter):
        """
        Args:
            ax:        The Matplotlib Axes object containing the line.
            line:      The Line2D object returned by ax.plot().
            formatter: A callable(x, y) → str that formats the annotation text.
        """
        self.ax = ax
        self.line = line
        self.formatter = formatter
        self.xs = np.array(line.get_xdata(), dtype=float)
        self.ys = np.array(line.get_ydata(), dtype=float)
        self.canvas = ax.figure.canvas

        # Create an invisible annotation — we'll show it on hover
        self.annotation = ax.annotate(
            "", xy=(0, 0), xytext=(15, 15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.8),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1"),
            visible=False,
        )

        # Listen for mouse movement over the plot
        self._cid = self.canvas.mpl_connect("motion_notify_event", self._on_move)

    def _on_move(self, event):
        """Called every time the mouse moves inside the figure."""
        # Hide annotation if the mouse leaves the axes area
        if event.inaxes != self.ax:
            if self.annotation.get_visible():
                self.annotation.set_visible(False)
                self.canvas.draw_idle()
            return

        # Find the data point closest to the mouse x-position
        idx = np.searchsorted(self.xs, event.xdata, side="left")
        idx = np.clip(idx, 1, len(self.xs) - 1)

        # Pick whichever of the two neighboring points is closer
        if abs(self.xs[idx - 1] - event.xdata) < abs(self.xs[idx] - event.xdata):
            idx -= 1

        # Update the annotation
        px, py = self.xs[idx], self.ys[idx]
        self.annotation.xy = (px, py)
        self.annotation.set_text(self.formatter(px, py))
        self.annotation.set_visible(True)
        self.canvas.draw_idle()


# =============================================================================
# Helper: Labeled Entry with Unit Selector
# =============================================================================
# Instead of a custom Item class, we use a simple function that creates a row
# of widgets (Label + Entry + unit button/combo) and returns a "getter" closure
# that reads the current value in SI units. This eliminates the need for a
# central data manager — each field knows how to read and convert itself.

def _make_param_row(parent, label_text, row, default_unit, *extra_units,
                    default_value="", entry_width=ENTRY_WIDTH,
                    readonly=False, use_combo=False, combo_values=None):
    """
    Creates one row of input widgets: [Label] [Entry] [Unit button or Combo].

    Returns a dictionary with:
        'get_value' — callable() → float (raw numeric value from the entry)
        'get_unit'  — callable() → str   (currently displayed unit string)
        'get_si'    — callable() → float (value converted to SI base unit)
        'set_value' — callable(str)       (set the entry text programmatically)
        'set_unit'  — callable(str)       (set the unit button/combo text)
        'entry'     — the tk.Entry widget (for read-only config, validation, etc.)
    """
    # --- Label ---
    ttk.Label(parent, text=label_text).grid(
        row=row, column=0, padx=PAD, pady=PAD, sticky="e"
    )

    # --- Entry ---
    # For combo-only rows (like End Correction), we skip the entry field
    if use_combo and combo_values:
        entry = None  # No entry widget for pure combobox rows
    else:
        entry = ttk.Entry(parent, width=entry_width)
        entry.grid(row=row, column=1, padx=PAD, pady=PAD, sticky="ew")
        if default_value != "":
            entry.insert(0, str(default_value))
        if readonly:
            entry.configure(state="readonly")

    # --- Unit selector (cycling button, combobox, or static label) ---
    all_units = [default_unit] + list(extra_units)
    unit_var = tk.StringVar(value=default_unit)

    if use_combo and combo_values:
        # Combobox mode — used for end correction and similar selection lists.
        # The combobox replaces the entry field entirely for this row.
        combo = ttk.Combobox(parent, values=combo_values, state="readonly", width=18)
        combo.set(combo_values[0])
        combo.grid(row=row, column=1, padx=PAD, pady=PAD, sticky="ew")
        get_unit_fn = combo.get
        set_unit_fn = combo.set
    elif len(all_units) > 1 and default_unit != "":
        # Cycling button mode — click to rotate through available units.
        # The button sits right next to the entry with minimal gap.
        def _cycle_unit(var=unit_var, options=all_units):
            current = var.get()
            idx = (options.index(current) + 1) % len(options)
            var.set(options[idx])
            btn.configure(text=options[idx])

        btn = ttk.Button(parent, textvariable=unit_var, width=6, command=_cycle_unit)
        btn.grid(row=row, column=2, padx=(2, PAD), pady=PAD, sticky="w")
        get_unit_fn = unit_var.get
        set_unit_fn = lambda val: (unit_var.set(val),)
    elif default_unit != "":
        # Single fixed unit — just show a static label close to the entry
        ttk.Label(parent, text=default_unit).grid(
            row=row, column=2, padx=(2, PAD), pady=PAD, sticky="w"
        )
        get_unit_fn = lambda: default_unit
        set_unit_fn = lambda val: None
    else:
        # No unit at all (e.g., "Number of Ports")
        get_unit_fn = lambda: ""
        set_unit_fn = lambda val: None

    # --- Build the accessor functions ---
    def get_value():
        if entry is None:
            raise ValueError(f"'{label_text}' has no numeric entry.")
        txt = entry.get().strip()
        if not txt:
            raise ValueError(f"'{label_text}' is empty.")
        return float(txt)

    def get_si():
        val = get_value()
        current_unit = get_unit_fn()
        if not current_unit:
            return val  # No unit conversion needed
        si_unit = units.get_si_unit(current_unit)
        return units.convert(val, current_unit, si_unit)

    def set_value(text):
        if entry is None:
            return
        state = entry.cget("state")
        if state == "readonly":
            entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, str(text))
        if state == "readonly":
            entry.configure(state="readonly")

    return {
        "get_value": get_value,
        "get_unit":  get_unit_fn,
        "get_si":    get_si,
        "set_value": set_value,
        "set_unit":  set_unit_fn,
        "entry":     entry,
    }


# =============================================================================
# Main Application Class
# =============================================================================

class App:
    """
    The top-level application. Creates the window, builds all widgets,
    and wires up the event handlers.
    """

    def __init__(self):
        # --- Main window ---
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)

        # Dictionary holding all parameter row accessors (from _make_param_row)
        self.fields = {}

        # --- Tabbed notebook ---
        notebook = ttk.Notebook(self.root)
        notebook.pack(expand=True, fill="both", padx=PAD, pady=PAD)

        input_tab = ttk.Frame(notebook)
        graph_tab = ttk.Frame(notebook)
        notebook.add(input_tab, text="Inputs")
        notebook.add(graph_tab, text="Graphs")

        # Build each tab
        self._build_input_tab(input_tab)
        self._build_graph_tab(graph_tab)

        # Center the window on screen after all widgets are laid out
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # -----------------------------------------------------------------
    # Input Tab
    # -----------------------------------------------------------------

    def _build_input_tab(self, parent):
        """Creates the Driver Parameters and Box Parameters groups."""

        # --- Driver Parameters ---
        drv = ttk.LabelFrame(parent, text="Driver Parameters")
        drv.grid(row=0, column=0, padx=PAD, pady=PAD, sticky="nw",
                 ipadx=PAD, ipady=PAD)

        # Each call creates a label + entry + unit widget row and returns
        # accessor functions stored in self.fields[key].
        self.fields["cms"] = _make_param_row(
            drv, "Cms", 0, "m/N", "mm/N", "um/N")
        self.fields["mms"] = _make_param_row(
            drv, "Mms", 1, "Kg", "g")
        self.fields["le"]  = _make_param_row(
            drv, "Le", 2, "H", "mH")
        self.fields["re"]  = _make_param_row(
            drv, "Re", 3, "ohm")
        self.fields["rms"] = _make_param_row(
            drv, "Rms", 4, "Kg/s")
        self.fields["bl"]  = _make_param_row(
            drv, "Bl", 5, "Tm", "N/A")
        self.fields["sd"]  = _make_param_row(
            drv, "Sd", 6, "m^2", "cm^2", "mm^2", "in^2", "ft^2")
        self.fields["vg"]  = _make_param_row(
            drv, "Vg", 7, "W")

        # --- Voice Coil Configuration ---
        self.vc_type_var   = tk.StringVar(value="Single VC")
        self.vc_wiring_var = tk.StringVar(value="Series")

        ttk.Label(drv, text="VC Type:").grid(
            row=8, column=0, padx=PAD, pady=PAD, sticky="e")
        ttk.Radiobutton(drv, text="Single", variable=self.vc_type_var,
                        value="Single VC", command=self._on_vc_type_change).grid(
            row=8, column=1, sticky="w", padx=PAD)
        ttk.Radiobutton(drv, text="Dual", variable=self.vc_type_var,
                        value="Dual VC", command=self._on_vc_type_change).grid(
            row=8, column=2, sticky="w")

        ttk.Label(drv, text="Dual VC Wiring:").grid(
            row=9, column=0, padx=PAD, pady=PAD, sticky="e")
        self.wiring_series = ttk.Radiobutton(
            drv, text="Series", variable=self.vc_wiring_var,
            value="Series", state="disabled")
        self.wiring_series.grid(row=9, column=1, sticky="w", padx=PAD)
        self.wiring_parallel = ttk.Radiobutton(
            drv, text="Parallel", variable=self.vc_wiring_var,
            value="Parallel", state="disabled")
        self.wiring_parallel.grid(row=9, column=2, sticky="w")

        # --- Box & Port Parameters ---
        box = ttk.LabelFrame(parent, text="Box & Port Parameters")
        box.grid(row=0, column=1, padx=PAD, pady=PAD, sticky="nw",
                 ipadx=PAD, ipady=PAD)

        self.fields["port_area"] = _make_param_row(
            box, "Port Cross Sectional Area", 0,
            "m^2", "cm^2", "mm^2", "in^2", "ft^2")
        self.fields["vb"] = _make_param_row(
            box, "Net Volume (Box)", 1,
            "m^3", "L", "cm^3", "mm^3", "in^3", "ft^3")
        self.fields["port_length"] = _make_param_row(
            box, "Length of Port", 2, "m", "cm", "mm", "in", "ft")
        self.fields["end_correction"] = _make_param_row(
            box, "End Correction", 3, "",
            use_combo=True, combo_values=END_CORRECTION_OPTIONS)
        self.fields["num_ports"] = _make_param_row(
            box, "Number of Ports", 4, "", default_value="1")

        # Port tuning output (read-only, "Hz" displayed inside the field)
        self.fields["fb_output"] = _make_param_row(
            box, "Port Tuning (fb)", 5, "", readonly=True)

        # --- Action Buttons ---
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=2, padx=PAD, pady=PAD, sticky="w")

        ttk.Button(btn_frame, text="Submit", command=self._on_submit).grid(
            row=0, column=0, padx=PAD, pady=PAD)
        ttk.Button(btn_frame, text="Load Test", command=self._on_load_test).grid(
            row=0, column=1, padx=PAD, pady=PAD)

    # -----------------------------------------------------------------
    # Graphs Tab
    # -----------------------------------------------------------------

    def _build_graph_tab(self, parent):
        """Creates the graph controls and the Matplotlib canvas."""

        # --- Controls bar across the top (single row layout) ---
        controls = ttk.Frame(parent)
        controls.pack(side="top", fill="x", padx=PAD, pady=(PAD, 0))

        # Graph type selector
        ttk.Label(controls, text="Select Graph:").pack(side="left", padx=(0, PAD))
        self.graph_type_var = tk.StringVar(value="Impedance")
        graph_options = [
            "Impedance",
            "Cone Excursion (mm)",
            "Port Velocity (m/s)",
            "Group Delay (ms)",
        ]
        graph_combo = ttk.Combobox(
            controls, textvariable=self.graph_type_var,
            values=graph_options, state="readonly", width=20)
        graph_combo.pack(side="left", padx=(0, PAD * 3))
        graph_combo.bind("<<ComboboxSelected>>", lambda e: self._update_graph())

        # Start Freq
        ttk.Label(controls, text="Start Freq").pack(side="left", padx=(0, 2))
        self.start_freq_entry = ttk.Entry(controls, width=6)
        self.start_freq_entry.insert(0, "10")
        self.start_freq_entry.pack(side="left", padx=(0, PAD * 2))

        # Stop Freq
        ttk.Label(controls, text="Stop Freq").pack(side="left", padx=(0, 2))
        self.stop_freq_entry = ttk.Entry(controls, width=6)
        self.stop_freq_entry.insert(0, "120")
        self.stop_freq_entry.pack(side="left", padx=(0, PAD * 2))

        # Step (Hz)
        ttk.Label(controls, text="Step (Hz)").pack(side="left", padx=(0, 2))
        self.step_entry = ttk.Entry(controls, width=6)
        self.step_entry.insert(0, "0.5")
        self.step_entry.pack(side="left", padx=(0, PAD * 3))

        # Update button
        ttk.Button(controls, text="Update Graph",
                   command=self._update_graph).pack(side="left", padx=(0, PAD))

        # --- Matplotlib canvas ---
        canvas_frame = ttk.Frame(parent)
        canvas_frame.pack(side="top", fill="both", expand=True, padx=PAD, pady=PAD)

        self.figure = Figure(figsize=(7, 4), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.grid(True, which="both", ls="--", c="0.7")
        self.figure.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.figure, master=canvas_frame)
        self.canvas.draw()

        toolbar = NavigationToolbar2Tk(self.canvas, canvas_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        # Keep a reference to the current SnapCursor so it isn't garbage-collected
        self._cursor = None

    # -----------------------------------------------------------------
    # Graph Tab Helpers — Read frequency range fields
    # -----------------------------------------------------------------

    def _get_start_freq(self):
        try:
            val = float(self.start_freq_entry.get())
            return max(val, 1)  # Enforce minimum of 1 Hz
        except ValueError:
            return 10  # Default fallback

    def _get_stop_freq(self):
        try:
            val = float(self.stop_freq_entry.get())
            start = self._get_start_freq()
            return val if val > start else start + 1
        except ValueError:
            return 120  # Default fallback

    def _get_step(self):
        try:
            val = float(self.step_entry.get())
            return val if val > 0 else 0.5
        except ValueError:
            return 0.5  # Default fallback

    # -----------------------------------------------------------------
    # Event Handlers
    # -----------------------------------------------------------------

    def _on_vc_type_change(self):
        """Enable/disable wiring radio buttons based on VC type selection."""
        state = "normal" if self.vc_type_var.get() == "Dual VC" else "disabled"
        self.wiring_series.configure(state=state)
        self.wiring_parallel.configure(state=state)

    def _on_submit(self):
        """Validate, compute port tuning, and draw the graph."""
        self._update_graph()

    def _on_load_test(self):
        """Populates all input fields with the reference test data."""
        td = test_data  # Shorthand

        # Driver parameters
        for key in ("re", "le", "bl", "sd", "cms", "mms", "rms"):
            self.fields[key]["set_value"](td.DRIVER[key])
            if key in td.DRIVER_DISPLAY_UNITS:
                self.fields[key]["set_unit"](td.DRIVER_DISPLAY_UNITS[key])

        # Vg
        self.fields["vg"]["set_value"](td.VG)

        # Box parameters
        for key in ("vb", "port_area", "port_length"):
            self.fields[key]["set_value"](td.BOX[key])
            if key in td.BOX_DISPLAY_UNITS:
                self.fields[key]["set_unit"](td.BOX_DISPLAY_UNITS[key])

        self.fields["num_ports"]["set_value"](td.BOX["num_ports"])
        self.fields["end_correction"]["set_unit"](td.BOX["end_correction"])

        # VC config
        self.vc_type_var.set(td.VC_TYPE)
        self.vc_wiring_var.set(td.VC_WIRING)
        self._on_vc_type_change()

        # Graph range
        self.start_freq_entry.delete(0, "end")
        self.start_freq_entry.insert(0, str(td.GRAPH_START_FREQ))
        self.stop_freq_entry.delete(0, "end")
        self.stop_freq_entry.insert(0, str(td.GRAPH_STOP_FREQ))
        self.step_entry.delete(0, "end")
        self.step_entry.insert(0, str(td.GRAPH_STEP))

        # Compute and display port tuning
        self._update_graph()

    # -----------------------------------------------------------------
    # Core: Gather Inputs → Run Physics → Plot
    # -----------------------------------------------------------------

    def _gather_inputs(self):
        """
        Reads every GUI field, applies unit conversions and VC adjustments,
        and returns (DriverParams, BoxParams, vg) ready for the physics engine.

        Raises ValueError with a descriptive message if any field is invalid.
        """
        # --- Read base driver values (converted to SI) ---
        re_base = self.fields["re"]["get_si"]()
        le_base = self.fields["le"]["get_si"]()
        bl_base = self.fields["bl"]["get_si"]()

        # --- Apply dual voice coil adjustments ---
        # When a driver has two voice coils, the effective electrical parameters
        # change depending on how the coils are wired:
        #   Series:   Re×2, Le×2, Bl×2
        #   Parallel: Re/2, Le/2, Bl stays the same
        re, le, bl = re_base, le_base, bl_base
        if self.vc_type_var.get() == "Dual VC":
            if self.vc_wiring_var.get() == "Series":
                re, le, bl = re_base * 2, le_base * 2, bl_base * 2
            else:  # Parallel
                re, le, bl = re_base / 2, le_base / 2, bl_base

        driver = physics.DriverParams(
            re=re, le=le, bl=bl,
            sd=self.fields["sd"]["get_si"](),
            cms=self.fields["cms"]["get_si"](),
            mms=self.fields["mms"]["get_si"](),
            rms=self.fields["rms"]["get_si"](),
        )

        # --- Box parameters ---
        ec_label = self.fields["end_correction"]["get_unit"]()
        ec_factor = END_CORRECTION_MAP.get(ec_label, 0.732)

        box = physics.BoxParams(
            vb=self.fields["vb"]["get_si"](),
            port_area=self.fields["port_area"]["get_si"](),
            port_length=self.fields["port_length"]["get_si"](),
            num_ports=int(self.fields["num_ports"]["get_value"]()),
            end_correction=ec_factor,
        )

        vg = self.fields["vg"]["get_si"]()

        return driver, box, vg

    def _update_graph(self):
        """Validates inputs, runs the analysis, and redraws the current graph."""
        # --- Step 1: Gather and validate inputs ---
        try:
            driver, box, vg = self._gather_inputs()
        except (ValueError, KeyError) as e:
            messagebox.showerror("Input Error", str(e))
            return

        # --- Step 2: Calculate and display port tuning ---
        fb = physics.calculate_port_tuning(box)
        self.fields["fb_output"]["set_value"](f"{fb:.2f} Hz")

        # --- Step 3: Build frequency array ---
        f_start = self._get_start_freq()
        f_stop  = self._get_stop_freq()
        f_step  = self._get_step()

        if f_start <= 0 or f_stop <= f_start or f_step <= 0:
            messagebox.showerror("Input Error",
                                 "Check graph range: need Start > 0, Stop > Start, Step > 0.")
            return

        num_points = int((f_stop - f_start) / f_step) + 1
        frequencies = np.linspace(f_start, f_stop, num=num_points)

        # --- Step 4: Run the physics engine across all frequencies ---
        try:
            results = physics.analyze_frequency_range(frequencies, driver, box, vg)
        except Exception as e:
            messagebox.showerror("Calculation Error", str(e))
            return

        # --- Step 5: Extract the selected data series for plotting ---
        graph_type = self.graph_type_var.get()
        freqs = np.array([r.frequency for r in results])

        if graph_type == "Impedance":
            y_data     = np.array([r.zin_magnitude for r in results])
            y_label    = "Impedance (Ohms)"
            log_scale  = True
            fmt        = lambda x, y: f"Freq: {x:.1f} Hz\nImp: {y:.1f} Ω"

        elif graph_type == "Cone Excursion (mm)":
            y_data     = np.array([r.cone_excursion_peak_mm for r in results])
            y_label    = "Cone Excursion (mm)"
            log_scale  = False
            fmt        = lambda x, y: f"Freq: {x:.1f} Hz\nExc: {y:.2f} mm"

        elif graph_type == "Port Velocity (m/s)":
            y_data     = np.array([r.port_velocity_peak_ms for r in results])
            y_label    = "Port Velocity (m/s)"
            log_scale  = False
            fmt        = lambda x, y: f"Freq: {x:.1f} Hz\nVel: {y:.2f} m/s"

        elif graph_type == "Group Delay (ms)":
            # Group delay = -d(phase)/d(omega), converted to milliseconds.
            # np.unwrap removes 2π discontinuities so the derivative is smooth.
            phases  = np.array([r.zin_phase_rad for r in results])
            omegas  = 2 * np.pi * freqs
            unwrapped = np.unwrap(phases)
            dphi_domega = np.gradient(unwrapped, omegas, edge_order=2)
            y_data  = -dphi_domega * 1000  # seconds → milliseconds
            y_label = "Group Delay (ms)"
            log_scale = False
            fmt     = lambda x, y: f"Freq: {x:.1f} Hz\nGD: {y:.2f} ms"

        else:
            # Fallback to impedance
            y_data     = np.array([r.zin_magnitude for r in results])
            y_label    = "Impedance (Ohms)"
            log_scale  = True
            fmt        = lambda x, y: f"Freq: {x:.1f} Hz\nImp: {y:.1f} Ω"

        # --- Step 6: Draw the plot ---
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Replace any non-finite values with NaN so Matplotlib skips them
        y_clean = np.where(np.isfinite(y_data), y_data, np.nan)
        line, = ax.plot(freqs, y_clean)

        ax.set_title(f"System {graph_type}")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel(y_label)
        ax.grid(True, which="both", ls="--", c="0.7")

        if log_scale:
            ax.set_yscale("log")
        else:
            ax.set_yscale("linear")
            y_min = np.nanmin(y_clean) if np.any(np.isfinite(y_clean)) else 0
            if y_min >= 0:
                ax.set_ylim(bottom=0)

        ax.set_xlim(f_start, f_stop)
        ax.set_xticks(np.linspace(f_start, f_stop, num=10, dtype=int))
        self.figure.tight_layout()

        # Attach the interactive snap cursor
        self._cursor = SnapCursor(ax, line, fmt)

        self.canvas.draw()

    # -----------------------------------------------------------------
    # Run
    # -----------------------------------------------------------------

    def run(self):
        """Starts the Tkinter main event loop."""
        self.root.mainloop()


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    app = App()
    app.run()