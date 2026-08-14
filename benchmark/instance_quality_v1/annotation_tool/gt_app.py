"""Tk GT annotation UI. This module imports GT-only data and has no candidate path."""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from benchmark.instance_quality_v1.annotation_tool.geometry import normalize_clip_bbox, screen_to_original
from benchmark.instance_quality_v1.annotation_tool.draft_store import DraftStore
from benchmark.instance_quality_v1.annotation_tool.gt_store import ENUMS, GroundTruthStore


ROOT = Path(__file__).resolve().parents[1]
HANDLE_SIZE = 7


class MetadataDialog(simpledialog.Dialog):
    def __init__(self, parent, store, image_id, bbox, existing=None):
        self.store, self.image_id, self.bbox, self.existing = store, image_id, bbox, existing
        self.result = None
        super().__init__(parent, "GT instance metadata")

    def body(self, master):
        current = self.existing or {}
        self.variables = {}
        fields = ["instance_id", "visibility", "scale", "crowding", "semantic_visibility"]
        defaults = [self.store.next_instance_id(self.image_id), "full", "medium", "isolated", "sufficient"]
        for row, (field, default) in enumerate(zip(fields, defaults)):
            ttk.Label(master, text=field).grid(row=row, column=0, sticky="w", padx=4, pady=3)
            variable = tk.StringVar(value=current.get(field, default))
            self.variables[field] = variable
            if field in ENUMS:
                widget = ttk.Combobox(master, textvariable=variable, values=ENUMS[field], state="readonly")
            else:
                widget = ttk.Entry(master, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", padx=4, pady=3)
        self.evaluable = tk.BooleanVar(value=current.get("evaluable", True))
        ttk.Checkbutton(master, text="evaluable", variable=self.evaluable).grid(row=5, column=0, columnspan=2, sticky="w", padx=4)
        ttk.Label(master, text="notes").grid(row=6, column=0, sticky="nw", padx=4)
        self.notes = tk.Text(master, width=44, height=5)
        self.notes.insert("1.0", current.get("notes", ""))
        self.notes.grid(row=6, column=1, padx=4, pady=3)
        return master

    def validate(self):
        try:
            value = {key: variable.get().strip() for key, variable in self.variables.items()}
            value.update({"bbox": self.bbox, "evaluable": bool(self.evaluable.get()), "notes": self.notes.get("1.0", "end").strip()})
            if not value["instance_id"]:
                raise ValueError("instance_id is required")
            if not value["evaluable"] and not value["notes"]:
                raise ValueError("evaluable=false requires notes")
            self.result = value
            return True
        except ValueError as error:
            messagebox.showerror("Invalid metadata", str(error), parent=self)
            return False


class AnnotationApp:
    def __init__(self, root_window, benchmark_root=ROOT):
        self.window = root_window
        self.store = GroundTruthStore(benchmark_root)
        self.drafts = DraftStore(benchmark_root)
        self.images = self.store.test_images
        self.index = 0
        self.zoom = 1.0
        self.offset = [0.0, 0.0]
        self.drag_mode = None
        self.drag_start = None
        self.drag_original_bbox = None
        self.selected_id = None
        self.photo = None
        self.image = None
        self._build()
        self.load_image(0)

    def _build(self):
        self.window.title("Visual Agent — Manual GT Annotation")
        self.window.geometry("1400x900")
        toolbar = ttk.Frame(self.window); toolbar.pack(fill="x")
        for text, command in [("◀ Previous", self.previous), ("Next ▶", self.next), ("Overview", self.overview), ("Load Assistant Draft", self.load_draft), ("Mark Image Complete", self.mark_complete), ("Freeze GT", self.freeze_gt), ("Reset Zoom", self.reset_zoom)]:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=3, pady=3)
        self.header = ttk.Label(toolbar, text=""); self.header.pack(side="left", padx=12)
        self.canvas = tk.Canvas(self.window, bg="#202124", highlightthickness=0); self.canvas.pack(fill="both", expand=True)
        self.status = ttk.Label(self.window, text="", anchor="w"); self.status.pack(fill="x")
        self.canvas.bind("<ButtonPress-1>", self.pointer_down)
        self.canvas.bind("<B1-Motion>", self.pointer_move)
        self.canvas.bind("<ButtonRelease-1>", self.pointer_up)
        self.canvas.bind("<Double-Button-1>", self.edit_selected_metadata)
        self.canvas.bind("<ButtonPress-2>", self.pan_start); self.canvas.bind("<B2-Motion>", self.pan_move)
        self.canvas.bind("<ButtonPress-3>", self.pan_start); self.canvas.bind("<B3-Motion>", self.pan_move)
        self.canvas.bind("<MouseWheel>", self.mouse_wheel)
        self.canvas.bind("<Motion>", self.show_cursor)
        self.window.bind("<Left>", lambda _e: self.previous()); self.window.bind("<Right>", lambda _e: self.next())
        self.window.bind("<Escape>", lambda _e: self.cancel()); self.window.bind("<Delete>", lambda _e: self.delete_selected())
        self.window.bind("<Control-s>", lambda _e: self.store.save()); self.window.bind("<Key-0>", lambda _e: self.reset_zoom())
        self.canvas.focus_set()

    @property
    def meta(self): return self.images[self.index]
    @property
    def entry(self): return self.store.image_entry(self.meta["image_id"])

    def load_image(self, index):
        self.index = max(0, min(len(self.images) - 1, index)); self.selected_id = None
        self.image = Image.open(self.store.root / self.meta["relative_path"]).convert("RGB")
        self.window.update_idletasks()
        self.zoom = min(max(0.05, (self.canvas.winfo_width() - 20) / self.image.width), max(0.05, (self.canvas.winfo_height() - 20) / self.image.height))
        self.offset = [(self.canvas.winfo_width() - self.image.width * self.zoom) / 2, (self.canvas.winfo_height() - self.image.height * self.zoom) / 2]
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        size = (max(1, round(self.image.width * self.zoom)), max(1, round(self.image.height * self.zoom)))
        self.photo = ImageTk.PhotoImage(self.image.resize(size, Image.Resampling.LANCZOS))
        self.canvas.create_image(self.offset[0], self.offset[1], image=self.photo, anchor="nw", tags="image")
        for item in self.entry["instances"]:
            x1, y1, x2, y2 = [item["bbox"][i] * self.zoom + self.offset[i % 2] for i in range(4)]
            color = "#00ffff" if item["instance_id"] == self.selected_id else "#00ff66"
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3, tags=("gt", item["instance_id"]))
            self.canvas.create_text(x1 + 3, y1 + 3, text=f"{item['instance_id']} {item['visibility']} {item['scale']}", fill="#101010", anchor="nw", tags=("gt", item["instance_id"]), font=("TkDefaultFont", 10, "bold"))
            self.canvas.create_rectangle(x1, y1, x1 + HANDLE_SIZE, y1 + HANDLE_SIZE, fill=color, tags=("handle", item["instance_id"]))
            self.canvas.create_rectangle(x2 - HANDLE_SIZE, y2 - HANDLE_SIZE, x2, y2, fill=color, tags=("handle", item["instance_id"]))
        progress = self.store.progress()
        self.header.config(text=f"{self.index + 1} / {len(self.images)}  {self.meta['image_id']}  {self.meta['scenario']}  target={self.meta['target_object']}  status={self.entry['annotation_status']}  review={self.entry['reviewed_by']}  GT={len(self.entry['instances'])}  completed={progress['completed']}/{progress['total']}")
        draft = self.drafts.image_entry(self.meta["image_id"])
        if draft:
            self.status.config(text=f"ASSISTANT DRAFT AVAILABLE ({len(draft['instances'])} boxes). Load, inspect, edit, then explicitly mark complete. {draft.get('review_note', '')}")

    def hit_instance(self, x, y):
        original = screen_to_original((x, y), self.zoom, self.offset)
        for item in reversed(self.entry["instances"]):
            x1, y1, x2, y2 = item["bbox"]
            if x1 <= original[0] <= x2 and y1 <= original[1] <= y2:
                margin = 10 / self.zoom
                resize = abs(original[0] - x2) < margin and abs(original[1] - y2) < margin
                return item, "resize" if resize else "move"
        return None, "draw"

    def pointer_down(self, event):
        if self.store.frozen: return
        item, mode = self.hit_instance(event.x, event.y)
        self.drag_mode = mode; self.drag_start = screen_to_original((event.x, event.y), self.zoom, self.offset)
        if item:
            self.selected_id = item["instance_id"]; self.drag_original_bbox = list(item["bbox"])
        else:
            self.selected_id = None
        self.redraw()

    def pointer_move(self, event):
        if not self.drag_mode: return
        current = screen_to_original((event.x, event.y), self.zoom, self.offset)
        if self.drag_mode == "draw":
            self.redraw(); a = [self.drag_start[i] * self.zoom + self.offset[i] for i in range(2)]
            self.canvas.create_rectangle(a[0], a[1], event.x, event.y, outline="#ffff00", width=2, dash=(4, 3), tags="draft")
        elif self.drag_mode in {"move", "resize"}:
            dx, dy = current[0] - self.drag_start[0], current[1] - self.drag_start[1]
            if self.drag_mode == "move":
                x1, y1, x2, y2 = self.drag_original_bbox
                width, height = x2 - x1, y2 - y1
                nx1 = min(max(0, x1 + dx), self.image.width - width); ny1 = min(max(0, y1 + dy), self.image.height - height)
                box = [nx1, ny1, nx1 + width, ny1 + height]
            else:
                box = normalize_clip_bbox(self.drag_original_bbox[:2], (self.drag_original_bbox[2] + dx, self.drag_original_bbox[3] + dy), self.image.width, self.image.height)
            self._preview_selected(box)

    def _preview_selected(self, box):
        self.redraw(); x1, y1, x2, y2 = [box[i] * self.zoom + self.offset[i % 2] for i in range(4)]
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffff00", width=3, dash=(4, 3), tags="draft")

    def pointer_up(self, event):
        if not self.drag_mode: return
        try:
            end = screen_to_original((event.x, event.y), self.zoom, self.offset)
            if self.drag_mode == "draw":
                box = normalize_clip_bbox(self.drag_start, end, self.image.width, self.image.height)
                dialog = MetadataDialog(self.window, self.store, self.meta["image_id"], box)
                if dialog.result: self.store.upsert_instance(self.meta["image_id"], dialog.result)
            else:
                existing = next(item for item in self.entry["instances"] if item["instance_id"] == self.selected_id)
                dx, dy = end[0] - self.drag_start[0], end[1] - self.drag_start[1]
                if self.drag_mode == "move":
                    x1, y1, x2, y2 = self.drag_original_bbox; w, h = x2 - x1, y2 - y1
                    nx1 = min(max(0, x1 + dx), self.image.width - w); ny1 = min(max(0, y1 + dy), self.image.height - h); box = [nx1, ny1, nx1 + w, ny1 + h]
                else: box = normalize_clip_bbox(self.drag_original_bbox[:2], (self.drag_original_bbox[2] + dx, self.drag_original_bbox[3] + dy), self.image.width, self.image.height)
                changed = dict(existing); changed["bbox"] = [round(v, 2) for v in box]
                self.store.upsert_instance(self.meta["image_id"], changed, self.selected_id)
        except ValueError as error:
            messagebox.showerror("Invalid bbox", str(error))
        finally:
            self.drag_mode = None; self.redraw()

    def pan_start(self, event): self.pan_anchor = (event.x, event.y, *self.offset)
    def pan_move(self, event):
        self.offset = [self.pan_anchor[2] + event.x - self.pan_anchor[0], self.pan_anchor[3] + event.y - self.pan_anchor[1]]; self.redraw()
    def mouse_wheel(self, event):
        old = self.zoom; self.zoom = min(12.0, max(0.05, self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
        original = screen_to_original((event.x, event.y), old, self.offset)
        self.offset = [event.x - original[0] * self.zoom, event.y - original[1] * self.zoom]; self.redraw()
    def show_cursor(self, event):
        point = screen_to_original((event.x, event.y), self.zoom, self.offset)
        self.status.config(text=f"original=({point[0]:.1f}, {point[1]:.1f})  zoom={self.zoom:.2f}x  image={self.image.width}×{self.image.height}  Draw: left drag | Pan: middle/right drag | Edit metadata: double-click selected")
    def reset_zoom(self): self.load_image(self.index)
    def previous(self): self.load_image(self.index - 1)
    def next(self): self.load_image(self.index + 1)
    def cancel(self): self.drag_mode = None; self.redraw()

    def delete_selected(self):
        if self.selected_id and messagebox.askyesno("Confirm delete", f"Delete {self.selected_id}? This does not renumber other IDs."):
            self.store.delete_instance(self.meta["image_id"], self.selected_id); self.selected_id = None; self.redraw()

    def edit_selected_metadata(self, _event=None):
        if not self.selected_id or self.store.frozen:
            return
        existing = next(item for item in self.entry["instances"] if item["instance_id"] == self.selected_id)
        dialog = MetadataDialog(self.window, self.store, self.meta["image_id"], list(existing["bbox"]), existing)
        if dialog.result:
            self.store.upsert_instance(self.meta["image_id"], dialog.result, self.selected_id)
            self.selected_id = dialog.result["instance_id"]
            self.redraw()

    def mark_complete(self):
        text = "确认已经检查完整张图片，包括远景、小目标和遮挡区域？"
        if messagebox.askyesno("Mark Image Complete", text):
            self.store.mark_complete(self.meta["image_id"], confirmed=True); self.redraw()

    def load_draft(self):
        draft = self.drafts.image_entry(self.meta["image_id"])
        if not draft:
            messagebox.showinfo("No draft", "No assistant visual draft exists for this image.")
            return
        replace = not self.entry["instances"]
        if not replace:
            replace = messagebox.askyesno("Replace current boxes?", "This image already has manual boxes. Replace them with the assistant draft? The image will remain IN_PROGRESS.")
            if not replace:
                return
        if not messagebox.askyesno("Load unverified draft", f"Load {len(draft['instances'])} assistant-drafted boxes? They are NOT ground truth until you inspect and explicitly mark the image complete.\n\n{draft.get('review_note', '')}"):
            return
        self.drafts.load_for_human_review(self.store, self.meta["image_id"], replace=True)
        self.selected_id = None
        self.redraw()

    def freeze_gt(self):
        try:
            fingerprint = self.store.freeze(); messagebox.showinfo("GT frozen", f"GT fingerprint:\n{fingerprint}"); self.redraw()
        except (ValueError, RuntimeError, PermissionError) as error: messagebox.showerror("Cannot freeze", str(error))

    def overview(self):
        window = tk.Toplevel(self.window); window.title("Annotation status")
        tree = ttk.Treeview(window, columns=("image_id", "scenario", "target", "status", "count"), show="headings", height=24)
        for key in ("image_id", "scenario", "target", "status", "count"): tree.heading(key, text=key)
        tree.pack(fill="both", expand=True)
        for meta in self.images:
            entry = self.store.image_entry(meta["image_id"]); tree.insert("", "end", iid=meta["image_id"], values=(meta["image_id"], meta["scenario"], meta["target_object"], entry["annotation_status"], len(entry["instances"])))
        counts = {}
        for meta in self.images:
            counts.setdefault(meta["scenario"], [0, 0]); counts[meta["scenario"]][1] += 1
            counts[meta["scenario"]][0] += self.store.image_entry(meta["image_id"])["annotation_status"] == "COMPLETE"
        scenario_text = " | ".join(f"{name}: {done}/{total}" for name, (done, total) in sorted(counts.items()))
        ttk.Label(window, text=f"Double-click a row to jump.\n{scenario_text}", justify="left").pack(fill="x")
        def jump(_event):
            selected = tree.selection()
            if selected: self.load_image(next(i for i, item in enumerate(self.images) if item["image_id"] == selected[0])); window.destroy()
        tree.bind("<Double-1>", jump)


def main():
    window = tk.Tk()
    AnnotationApp(window)
    window.mainloop()


if __name__ == "__main__": main()
