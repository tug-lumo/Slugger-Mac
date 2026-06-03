# SLUGGER — Mac Setup Instructions

> First time only. After this, just double-click to launch.

---

## Step 1 — Check Python is installed

Open **Terminal** (press `⌘ Space`, type `Terminal`, hit Enter).

Type this and press Enter:

```
python3 --version
```

You should see something like `Python 3.11.4`. If you get an error, download Python from **python.org/downloads** and install it, then come back here.

---

## Step 2 — Find the app folder in Terminal

In Terminal, type `cd ` (with a space after it), then drag the **screenplay_reader - Mac** folder from Finder into the Terminal window. The path will fill in automatically. Press Enter.

---

## Step 3 — Make the launcher executable (one time only)

Type this and press Enter:

```
chmod +x run.command
```

You won't see any confirmation — that's normal.

---

## Step 4 — Launch the app

Go to the **screenplay_reader - Mac** folder in Finder and double-click **run.command**.

A Terminal window will open. It will:
- Create a virtual environment (first run only — takes ~30 seconds)
- Install all dependencies automatically
- Open the app in your browser at `http://localhost:8501`

---

## Every time after that

Just double-click **run.command**. No other steps needed.

To stop the app, click the Terminal window and press `Ctrl+C`.

---

## Troubleshooting

**"Permission denied" when double-clicking** — you need to repeat Step 3.

**Browser doesn't open automatically** — open your browser manually and go to `http://localhost:8501`.

**App won't start / red errors in Terminal** — check that Python 3 is installed (Step 1) and that you're in the right folder (Step 2).
