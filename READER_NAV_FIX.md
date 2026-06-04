# Reader Navigation Fix — Instructions for Mac Claude

**The correct code is already in this repo.** Do NOT rewrite navigation logic
from scratch. Just run `git pull` and restart the server.

---

## Verify the fix is present

After `git pull`, open `app.py` and confirm ALL of the following are true:

### 1. No `_rdr_prev_scene` or `_rdr_prev_page` anywhere

```bash
grep -n "_rdr_prev" app.py
```
Should return **nothing**. If those variables exist, the fix is not in place.

### 2. Simple reads at the top of the Reader tab (no sync logic)

Find the line `with tab_reader:` and look just below it. You should see:

```python
    scene_idx = max(0, min(st.session_state.get("scene_jump_select", 0), n_scenes - 1))
    page_idx  = max(0, min(st.session_state.get("reader_page_idx", 0), total_pages - 1))
    scene     = scenes[scene_idx]
```

There should be NO `if _rdr_this_scene != _rdr_prev_scene:` block anywhere nearby.

### 3. Page nav buttons set BOTH variables and call st.rerun()

Find the `btn_prev_page` and `btn_next_page` buttons. Each must look like:

```python
        with _pg1:
            if st.button("◀", key="btn_prev_page", use_container_width=True):
                _np = max(0, page_idx - 1)
                st.session_state["reader_page_idx"] = _np
                if not st.session_state.get("_scene_pinned", False):
                    st.session_state["scene_jump_select"] = _scene_for_page(scenes, _np)
                st.rerun()
        with _pg3:
            if st.button("▶", key="btn_next_page", use_container_width=True):
                _np = min(total_pages - 1, page_idx + 1)
                st.session_state["reader_page_idx"] = _np
                if not st.session_state.get("_scene_pinned", False):
                    st.session_state["scene_jump_select"] = _scene_for_page(scenes, _np)
                st.rerun()
```

### 4. Scene nav buttons set BOTH variables and call st.rerun()

Find `btn_prev_scene` and `btn_next_scene`. Each must set both
`scene_jump_select` AND `reader_page_idx` then call `st.rerun()`:

```python
        with _cn_prev:
            if st.button("◀ Prev", use_container_width=True, key="btn_prev_scene"):
                if scene_idx > 0:
                    _tgt = scene_idx - 1
                    st.session_state["scene_jump_select"] = _tgt
                    if not getattr(scenes[_tgt], "manually_added", False):
                        st.session_state["reader_page_idx"] = int(scenes[_tgt].page_start)
                    st.rerun()
        with _cn_next:
            if st.button("Next ▶", use_container_width=True, key="btn_next_scene"):
                if scene_idx < n_scenes - 1:
                    _tgt = scene_idx + 1
                    st.session_state["scene_jump_select"] = _tgt
                    if not getattr(scenes[_tgt], "manually_added", False):
                        st.session_state["reader_page_idx"] = int(scenes[_tgt].page_start)
                    st.rerun()
```

### 5. Scene dropdown has on_change handler

The `scene_jump_select` selectbox must have `on_change=_on_scene_jump`:

```python
            st.selectbox(
                "Jump to scene", options=range(n_scenes),
                format_func=lambda i: scene_labels[i],
                key="scene_jump_select", label_visibility="collapsed",
                on_change=_on_scene_jump,
            )
```

And `_on_scene_jump` is defined just above the nav columns:

```python
        def _on_scene_jump():
            idx = st.session_state["scene_jump_select"]
            _sc = scenes[idx] if 0 <= idx < len(scenes) else None
            if _sc and not getattr(_sc, "manually_added", False):
                st.session_state["reader_page_idx"] = int(_sc.page_start)
```

---

## If any of the above checks fail

The fix is missing. Copy the exact code blocks above into the correct
locations in `app.py`. Do not add `_rdr_prev_scene` or `_rdr_prev_page`
back under any circumstances — those variables are what caused the bugs.

## Why the old code was broken

The old code detected "which thing changed" by comparing current vs previous
values of scene/page. Page nav buttons had no `st.rerun()`, so the page
change was delayed one render. On the next interaction, the stale prev-values
caused the sync to fire in the wrong direction — producing scene jumps,
back-nav going to higher scenes, and needing to press page buttons twice.

The fix: every nav action atomically writes BOTH state variables then reruns.
No inference needed at render time.
