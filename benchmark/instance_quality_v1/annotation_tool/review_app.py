"""Explicit candidate-review UI. Never imported by the default GT entry point."""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from benchmark.instance_quality_v1.annotation_tool.review_store import CandidateReviewStore
from benchmark.instance_quality_v1.schema import COMPLETENESS, REVIEW_CLASSES


ROOT = Path(__file__).resolve().parents[1]


class ReviewApp:
    def __init__(self, window, benchmark_root=ROOT):
        self.window = window
        self.store = CandidateReviewStore(benchmark_root)
        self.images = self.store.raw["images"]
        self.image_index = 0
        self.candidate_index = 0
        self.photo = None
        self._build()
        self.load_image(0)

    def _build(self):
        self.window.title("Visual Agent — Detector Candidate Review")
        self.window.geometry("1400x900")
        bar = ttk.Frame(self.window); bar.pack(fill="x")
        ttk.Button(bar, text="◀ Image", command=lambda: self.load_image(self.image_index - 1)).pack(side="left")
        ttk.Button(bar, text="Image ▶", command=lambda: self.load_image(self.image_index + 1)).pack(side="left")
        ttk.Button(bar, text="◀ Candidate", command=lambda: self.load_candidate(self.candidate_index - 1)).pack(side="left")
        ttk.Button(bar, text="Candidate ▶", command=lambda: self.load_candidate(self.candidate_index + 1)).pack(side="left")
        ttk.Button(bar, text="Save Review", command=self.save).pack(side="left")
        ttk.Button(bar, text="Mark Review Complete", command=self.mark_complete).pack(side="left")
        self.header = ttk.Label(bar); self.header.pack(side="left", padx=10)
        body = ttk.Panedwindow(self.window, orient="horizontal"); body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#202124", width=1000); body.add(self.canvas, weight=4)
        form = ttk.Frame(body); body.add(form, weight=1)
        self.classification = tk.StringVar(); self.completeness = tk.StringVar(); self.mapped = tk.StringVar()
        for row, (label, variable, values) in enumerate([
            ("classification", self.classification, sorted(REVIEW_CLASSES)),
            ("mapped GT", self.mapped, []),
            ("completeness", self.completeness, sorted(COMPLETENESS)),
        ]):
            ttk.Label(form, text=label).grid(row=row * 2, column=0, sticky="w", pady=(10, 2))
            box = ttk.Combobox(form, textvariable=variable, values=values, state="readonly"); box.grid(row=row * 2 + 1, column=0, sticky="ew");
            if label == "mapped GT": self.mapped_box = box
        ttk.Label(form, text="review_notes").grid(row=6, column=0, sticky="w", pady=(10, 2))
        self.notes = tk.Text(form, width=35, height=12); self.notes.grid(row=7, column=0, sticky="nsew")
        ttk.Label(form, text="No automatic matching or classification.\nGT=green; current candidate=yellow; other candidates=red.", foreground="#aa0000").grid(row=8, column=0, sticky="w", pady=12)
        form.columnconfigure(0, weight=1); form.rowconfigure(7, weight=1)

    @property
    def row(self): return self.images[self.image_index]
    @property
    def candidates(self): return self.row["candidates"]

    def load_image(self, index):
        self.image_index = max(0, min(len(self.images) - 1, index)); self.candidate_index = 0
        self.load_candidate(0)

    def load_candidate(self, index):
        if self.candidates: self.candidate_index = max(0, min(len(self.candidates) - 1, index))
        else: self.candidate_index = 0
        gt_ids = [""] + [item["instance_id"] for item in self.store.gt.image_entry(self.row["image_id"])["instances"]]
        self.mapped_box.configure(values=gt_ids)
        self.classification.set(""); self.completeness.set(""); self.mapped.set(""); self.notes.delete("1.0", "end")
        if self.candidates:
            candidate_id = self.candidates[self.candidate_index]["id"]
            existing = next((item for item in self.store.review_image(self.row["image_id"])["candidates"] if item["candidate_id"] == candidate_id), None)
            if existing:
                self.classification.set(existing["classification"]); self.completeness.set(existing["completeness"]); self.mapped.set(existing["mapped_gt_instance_id"] or ""); self.notes.insert("1.0", existing["review_notes"])
        self.redraw()

    def redraw(self):
        meta = self.store.gt.image_meta(self.row["image_id"]); image = Image.open(self.store.root / meta["relative_path"]).convert("RGB")
        cw, ch = max(100, self.canvas.winfo_width()), max(100, self.canvas.winfo_height()); zoom = min((cw - 20) / image.width, (ch - 20) / image.height)
        size = (round(image.width * zoom), round(image.height * zoom)); self.photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS)); self.canvas.delete("all")
        ox, oy = (cw - size[0]) / 2, (ch - size[1]) / 2; self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        def box(value, color, label, width):
            coords = [value[i] * zoom + (ox if i % 2 == 0 else oy) for i in range(4)]; self.canvas.create_rectangle(*coords, outline=color, width=width); self.canvas.create_text(coords[0] + 3, coords[1] + 3, text=label, fill=color, anchor="nw", font=("TkDefaultFont", 10, "bold"))
        for item in self.store.gt.image_entry(self.row["image_id"])["instances"]: box(item["bbox"], "#00ff66", f"GT {item['instance_id']}", 3)
        for index, item in enumerate(self.candidates): box(item["bbox"], "#ffff00" if index == self.candidate_index else "#ff4040", f"Candidate {item['id']}", 3 if index == self.candidate_index else 1)
        current = f"candidate {self.candidate_index + 1}/{len(self.candidates)}" if self.candidates else "zero candidates"
        self.header.config(text=f"image {self.image_index + 1}/{len(self.images)}  {self.row['image_id']}  {current}")

    def save(self):
        if not self.candidates: return
        review = {"candidate_id": self.candidates[self.candidate_index]["id"], "mapped_gt_instance_id": self.mapped.get() or None, "classification": self.classification.get(), "completeness": self.completeness.get(), "review_notes": self.notes.get("1.0", "end").strip()}
        try: self.store.save_review(self.row["image_id"], review); self.load_candidate(self.candidate_index)
        except ValueError as error: messagebox.showerror("Invalid review", str(error))

    def mark_complete(self):
        try: self.store.mark_complete(self.row["image_id"]); messagebox.showinfo("Complete", "All raw candidates have a manual review.")
        except RuntimeError as error: messagebox.showerror("Cannot complete", str(error))


def main():
    window = tk.Tk(); ReviewApp(window); window.mainloop()


if __name__ == "__main__": main()
