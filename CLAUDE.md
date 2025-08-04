# Project Context: NASA Mission Spending Tracker

## 1. Project Goal

The goal is to build an object-oriented Python system for generating a static reference website for NASA science missions. The architecture emphasizes a clean separation of concerns, with distinct classes for data representation, data processing, and site rendering. This modular, OO approach ensures the system is maintainable, scalable, and easy to debug.

---

## 2. Core Technologies & Principles

-   **Architecture**: Object-Oriented Programming (OOP)
-   **Key Libraries**: `Pydantic`, `pandas`, `ruamel.yaml`, `Jinja2`, `Plotly`
-   **CLI**: `argparse`
-   **Custom Library**: A local library (`usaspending`) for the USAspending.gov API.
-   **Automation**: GitHub Actions

IMPORTANT: Reference the API documentarion for the `usaspending` library to understand how to interact with the API endpoints and data structures in the local file `usaspending.md`.
---

## 3. Project Structure

[project_root]/
├── data/missions/
├── scripts/
│   ├── core/                       # Core object-oriented modules
│   │   ├── init.py
│   │   ├── mission.py              # Defines the Mission class
│   │   ├── processors.py           # Defines data calculator classes
│   │   └── renderer.py             # Defines the SiteGenerator class
│   ├── calculate_outlays.py        # CLI to run the OutlaysCalculator
│   ├── calculate_spending_map.py   # CLI to run the MapDataCalculator
│   └── generate_site.py            # CLI to run the SiteGenerator
├── site/
├── templates/
└── requirements.txt

---

## 4. Object-Oriented Design

### The Core (`scripts/core/`)

-   **`mission.py: Mission`**: The central class. An instance represents a single NASA mission. It's responsible for loading, validating (via an internal Pydantic model), and providing access to its own data.
-   **`processors.py: *Calculator`**: Contains classes like `OutlaysCalculator` and `MapDataCalculator`. Each class is responsible for a single data processing task. They take a `Mission` object, perform their calculations, and return a pandas DataFrame.
-   **`renderer.py: SiteGenerator`**: A class responsible for presentation. It takes a `Mission` object and the paths to pre-calculated data caches and renders all final output files (`index.html`, `data.json`).

### The Interface (`scripts/*.py`)

-   The scripts in the root `scripts/` directory are **thin CLI wrappers**.
-   Their job is to parse command-line arguments (e.g., a file path or a directory path).
-   They instantiate and orchestrate the core objects from `scripts/core/`. For example, `calculate_outlays.py` will create an `OutlaysCalculator` instance and pass `Mission` objects to it in a loop.
-   This design cleanly separates the application's core logic from its command-line interface.

---

## 5. Coding Style & Instructions

-   Implement the design using clean, pythonic, object-oriented principles.
-   Adhere strictly to **PEP 8**. Use `pathlib` for all file system path manipulations.
-   When I ask you to generate a script, please follow the object-oriented and modular logic outlined in this document precisely. A CLI script should instantiate and call the core classes, not contain the business logic itself.