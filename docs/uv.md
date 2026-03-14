# uv Package Manager Usage Guide

This guide provides a clean and structured overview of using the `uv` package and environment manager in Python projects, including compatibility with `pip` users.

---

## 🚀 Project Setup with uv

### 1. Install `uv`

Install `uv` globally using pip:

```bash
pip install uv
```

---

### 2. Initialize a New Project (optional)

If you're starting a new project:

```bash
uv init
```

This creates a `pyproject.toml` file.

---

### 3. Create a Virtual Environment

```bash
uv venv --python 3.13
```

This creates a virtual environment in the `.venv/` directory.

---

### 4. Activate the Virtual Environment

**macOS / Linux**

```bash
source .venv/bin/activate
```

**Windows**

```bash
.venv\Scripts\activate
```

---

## 📦 Installing Dependencies

### From `requirements.txt`

```bash
uv add -r requirements.txt
```

This adds the dependencies to `pyproject.toml` and installs them into the environment.

---

### Sync Using the Lockfile (Exact Versions)

```bash
uv sync --frozen
```

Installs dependencies exactly as pinned in `uv.lock`.

---

## 🔁 Exporting Dependencies for pip Users

To allow users **without uv** to install dependencies using pip, export a compatible `requirements.txt` file.

### Fully reproducible (with hashes)

```bash
uv export > requirements.txt
```

Install using pip:

```bash
pip install --require-hashes -r requirements.txt
```

---

### Pip-friendly (no hashes)

```bash
uv export --no-hashes > requirements.txt
```

Install using pip:

```bash
pip install -r requirements.txt
```

---

## 🛠 Common uv Commands

Add a new dependency:

```bash
uv add <package>
```

Update all dependencies:

```bash
uv sync
```

Run a command inside the environment:

```bash
uv run <command>
```

---

## ❗ Troubleshooting

### Dependency conflicts

```bash
uv sync
```

---

### Python version mismatch

Ensure Python **3.13** is installed and correctly referenced by your shell or IDE.

---

## ✅ Recommended Repo Layout

For best compatibility:

* `pyproject.toml` – source of truth
* `uv.lock` – exact, reproducible dependency lock
* `requirements.txt` – for pip-only users

---