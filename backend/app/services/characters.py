"""Character system (PLAN.md section 11).

Flow: brief -> 4 candidates -> pick -> lock-and-edit (versions) -> sheet
(front/side/three-quarter + happy/sleepy/surprised) -> consistency test
(3 scenes, vision check vs sheet) -> approve (pass or override) -> sample
page -> approve. Approved characters can be saved to the library and reused.
"""

from __future__ import annotations

import io
import shutil
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from ..models import Book, Character, CharacterAsset
from ..providers.base import usage_context
from ..providers.registry import get_image_provider
from ..schemas import CharacterBriefsOut, CharacterEditOut, VisionVerdict
from . import storage
from .analysis import recipe_text
from .llm import structured
from .prompts import NO_TEXT_RULE

SHEET_VIEWS = ("front", "side", "three-quarter")
EXPRESSIONS = ("happy", "sleepy", "surprised")
TEST_SCENES = (
    "walking along a garden path, full body",
    "sitting and holding a small cup, three-quarter view",
    "waving hello next to a simple tree",
)
N_CANDIDATES = 4


class GateError(ValueError):
    """An approval gate is not satisfied."""


# ------------------------------------------------------------ style anchor


def default_style_rules(book: Book) -> str:
    r = book.recipe
    lw = (r.line_weight if r and r.line_weight else "bold")
    detail = (r.detail_level if r and r.detail_level else "low")
    age = (r.age_group if r and r.age_group else "4-8")
    return (f"Black and white coloring-book line art. {lw} clean black outlines of even weight, pure white "
            f"background, no shading, no grey, no gradients, no filled black areas, closed shapes. Detail level: "
            f"{detail}. Cute rounded shapes suitable for ages {age}. Simple background. {NO_TEXT_RULE}")


def style_anchor(book: Book) -> tuple[str, list[bytes]]:
    """Rules + reference images attached to every later generation."""
    sa = book.style_anchor or {}
    rules = sa.get("rules") or default_style_rules(book)
    refs = []
    data = storage.read_bytes(sa.get("reference_path"))
    if data:
        refs.append(data)
    return rules, refs


def set_style_anchor(session: Session, book: Book, rules: str | None = None, reference_path: str | None = None) -> dict:
    sa = dict(book.style_anchor or {})
    if rules is not None:
        sa["rules"] = rules.strip()
    if reference_path is not None:
        sa["reference_path"] = reference_path
    sa.setdefault("rules", default_style_rules(book))
    book.style_anchor = sa
    session.commit()
    return sa


# --------------------------------------------------------------- helpers


def _save_png(data: bytes, path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("L")
        im.save(path, format="PNG")
    return storage.rel(path)


def describe(c: Character) -> str:
    outfit = (c.brief or {}).get("outfit") or "none"
    return (f"{c.name}: a {c.species}; proportions: {c.proportions}; signature feature: {c.signature_feature}; "
            f"outfit: {outfit}; personality: {c.personality}")


def base_prompt(c: Character, rules: str, view: str = "front view, full body, standing, neutral pose") -> str:
    return (f"Character design of {c.name}, a {c.species}. {c.proportions}. Signature feature: {c.signature_feature}. "
            f"Outfit: {(c.brief or {}).get('outfit') or 'none'}. Personality: {c.personality}. {view}. "
            f"Plain white background, single character centered with margin. {rules}")


def selected_asset(c: Character) -> CharacterAsset | None:
    cands = [a for a in c.assets if a.kind == "candidate"]
    return next((a for a in reversed(cands) if a.selected), None)


def sheet_images(c: Character, max_n: int = 3) -> list[bytes]:
    """Best references for this character: sheet front view, selected image."""
    out: list[bytes] = []
    front = next((a for a in c.assets if a.kind == "sheet" and (a.meta or {}).get("view") == "front"), None)
    sel = selected_asset(c)
    for a in (front, sel):
        if a is not None:
            d = storage.read_bytes(a.path)
            if d:
                out.append(d)
    return out[:max_n]


def _char_dir(c: Character):
    return storage.characters_dir(c.book_id) / str(c.id)


def _versions(c: Character) -> list[dict[str, Any]]:
    return list((c.brief or {}).get("versions") or [])


def _update_brief(c: Character, **kw: Any) -> None:
    b = dict(c.brief or {})
    b.update(kw)
    c.brief = b


def _reset_after_change(c: Character) -> None:
    """Changing the look invalidates sheet, test and approval."""
    for a in list(c.assets):
        if a.kind in ("sheet", "expression", "test_scene"):
            c.assets.remove(a)
    _update_brief(c, consistency=None)
    c.status = "draft"


# ----------------------------------------------------------------- briefs


def generate_briefs(session: Session, book: Book, count: int = 1) -> list[Character]:
    from .planning import chosen_theme

    theme = chosen_theme(book)
    out = structured("character_brief",
                     {"theme": f"{theme.title}: {theme.description}" if theme else book.title,
                      "recipe": recipe_text(book.recipe), "count": count}, CharacterBriefsOut)
    created = []
    for cb in out.characters[:count]:
        c = Character(book_id=book.id, name=cb.name.strip(), species=cb.species, personality=cb.personality,
                      proportions=cb.proportions, signature_feature=cb.signature_feature,
                      brief={"outfit": cb.outfit, "versions": []}, status="draft")
        session.add(c)
        created.append(c)
    if book.status in ("draft", "analyzed", "themed"):
        book.status = "characters"
    session.commit()
    return created


def update_brief(session: Session, c: Character, fields: dict[str, Any]) -> Character:
    for k in ("name", "species", "personality", "proportions", "signature_feature"):
        if k in fields and fields[k] is not None:
            setattr(c, k, str(fields[k]))
    if "outfit" in fields:
        _update_brief(c, outfit=fields["outfit"])
    session.commit()
    return c


# ------------------------------------------------------------- candidates


def generate_candidates(session: Session, book: Book, c: Character, n: int = N_CANDIDATES, progress=lambda p, m=None: None) -> list[CharacterAsset]:
    rules, refs = style_anchor(book)
    prompt = base_prompt(c, rules)
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    out = []
    # new round of candidates replaces previous unselected candidates
    for a in list(c.assets):
        if a.kind == "candidate" and not a.selected:
            c.assets.remove(a)
    version = len(_versions(c)) + 1
    with usage_context(book_id=book.id, purpose="character"):
        for i in range(n):
            data = provider.generate(prompt, (1024, 1024), reference_images=refs, seed=1000 * version + i)
            path = _save_png(data, _char_dir(c) / f"candidate_v{version}_{i}.png")
            a = CharacterAsset(character_id=c.id, kind="candidate", path=path,
                               meta={"version": version, "seed": 1000 * version + i, "prompt": prompt, "round": version})
            c.assets.append(a)
            out.append(a)
            progress((i + 1) / n, f"candidate {i + 1}/{n}")
    _update_brief(c, prompt=prompt, versions=_versions(c) + [{"version": version, "kind": "candidates", "prompt": prompt}])
    session.commit()
    return out


def select_candidate(session: Session, book: Book, c: Character, asset_id: int) -> CharacterAsset:
    target = None
    for a in c.assets:
        if a.kind == "candidate":
            a.selected = a.id == asset_id
            if a.selected:
                target = a
    if target is None:
        raise KeyError(f"candidate {asset_id} not found")
    _update_brief(c, prompt=(target.meta or {}).get("prompt") or (c.brief or {}).get("prompt"))
    _reset_after_change(c)
    # first selected character image becomes the style reference
    if not (book.style_anchor or {}).get("reference_path"):
        set_style_anchor(session, book, reference_path=target.path)
    session.commit()
    return target


def edit_character(session: Session, book: Book, c: Character, instruction: str) -> CharacterAsset:
    sel = selected_asset(c)
    if sel is None:
        raise GateError("select a candidate before editing")
    rules, _ = style_anchor(book)
    current = (sel.meta or {}).get("prompt") or base_prompt(c, rules)
    out = structured("character_edit", {"character": describe(c), "base_prompt": current, "instruction": instruction},
                     CharacterEditOut)
    ref = storage.read_bytes(sel.path)
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    version = len(_versions(c)) + 1
    with usage_context(book_id=book.id, purpose="character"):
        data = provider.generate(out.prompt, (1024, 1024), reference_images=[ref] if ref else [], seed=1000 * version)
    path = _save_png(data, _char_dir(c) / f"edit_v{version}.png")
    for a in c.assets:
        if a.kind == "candidate":
            a.selected = False
    asset = CharacterAsset(character_id=c.id, kind="candidate", path=path, selected=True,
                           meta={"version": version, "prompt": out.prompt, "instruction": instruction,
                                 "parent_id": sel.id, "changed": out.changed})
    c.assets.append(asset)
    _update_brief(c, prompt=out.prompt, versions=_versions(c) + [
        {"version": version, "kind": "edit", "instruction": instruction, "parent_id": sel.id, "prompt": out.prompt}])
    _reset_after_change(c)
    session.commit()
    return asset


def revert_to(session: Session, book: Book, c: Character, asset_id: int) -> CharacterAsset:
    """Pick an older version from the history."""
    return select_candidate(session, book, c, asset_id)


# ------------------------------------------------------------------ sheet


def generate_sheet(session: Session, book: Book, c: Character, progress=lambda p, m=None: None) -> list[CharacterAsset]:
    sel = selected_asset(c)
    if sel is None:
        raise GateError("select a candidate before generating the sheet")
    ref = storage.read_bytes(sel.path)
    rules, style_refs = style_anchor(book)
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    for a in list(c.assets):
        if a.kind in ("sheet", "expression"):
            c.assets.remove(a)
    jobs = [("sheet", v, f"{v} view, full body, neutral expression") for v in SHEET_VIEWS] + \
           [("expression", e, f"head and shoulders, {e} expression") for e in EXPRESSIONS]
    out = []
    with usage_context(book_id=book.id, purpose="character"):
        for i, (kind, key, view) in enumerate(jobs):
            prompt = base_prompt(c, rules, view) + " Keep the character identical to the reference image."
            data = provider.generate(prompt, (1024, 1024), reference_images=[ref] if ref else [], seed=7000 + i)
            path = _save_png(data, _char_dir(c) / f"{kind}_{key}.png")
            a = CharacterAsset(character_id=c.id, kind=kind, path=path,
                               meta={"view" if kind == "sheet" else "expression": key, "prompt": prompt})
            c.assets.append(a)
            out.append(a)
            progress((i + 1) / len(jobs), f"{key}")
    _update_brief(c, consistency=None)
    c.status = "draft"
    session.commit()
    return out


# ------------------------------------------------------------ consistency


def run_consistency_test(session: Session, book: Book, c: Character, progress=lambda p, m=None: None) -> dict[str, Any]:
    if not any(a.kind == "sheet" for a in c.assets):
        raise GateError("generate the character sheet first")
    rules, _ = style_anchor(book)
    refs = sheet_images(c)
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    for a in list(c.assets):
        if a.kind == "test_scene":
            c.assets.remove(a)
    results = []
    with usage_context(book_id=book.id, purpose="consistency"):
        for i, scene in enumerate(TEST_SCENES):
            prompt = (f"{c.name} the {c.species} {scene}. Keep {c.name} identical to the reference character sheet, "
                      f"including the signature feature ({c.signature_feature}). {rules}")
            data = provider.generate(prompt, (1024, 1024), reference_images=refs, seed=9000 + i)
            path = _save_png(data, _char_dir(c) / f"test_{i}.png")
            verdict = structured("consistency_check",
                                 {"character": describe(c), "signature_feature": c.signature_feature},
                                 VisionVerdict, images=[data] + refs)
            a = CharacterAsset(character_id=c.id, kind="test_scene", path=path,
                               meta={"scene": scene, "verdict": verdict.as_dict()})
            c.assets.append(a)
            results.append({"asset_id": None, "scene": scene, **verdict.as_dict()})
            progress((i + 1) / len(TEST_SCENES), f"test scene {i + 1}")
    session.flush()
    tests = [a for a in c.assets if a.kind == "test_scene"]
    for r, a in zip(results, tests):
        r["asset_id"] = a.id
    passed = all(r["pass"] for r in results)
    consistency = {"pass": passed, "results": results, "override": False}
    _update_brief(c, consistency=consistency)
    session.commit()
    return consistency


def approve_character(session: Session, c: Character, override: bool = False) -> Character:
    cons = (c.brief or {}).get("consistency")
    if cons is None:
        raise GateError("run the consistency test before approving")
    if not cons.get("pass") and not override:
        raise GateError("consistency test did not pass; fix the character or approve with override")
    if override and not cons.get("pass"):
        _update_brief(c, consistency={**cons, "override": True})
    c.status = "approved"
    session.commit()
    return c


def unapprove(session: Session, c: Character) -> Character:
    c.status = "draft"
    session.commit()
    return c


# ------------------------------------------------------------- sample page


def characters_ready(session: Session, book: Book) -> bool:
    chars = session.query(Character).filter(Character.book_id == book.id).all()
    return all(c.status == "approved" for c in chars)


def generate_sample(session: Session, book: Book) -> dict[str, Any]:
    if not characters_ready(session, book):
        raise GateError("approve all characters before the sample page")
    from .generation import build_image_prompt, image_size_hint

    chars = session.query(Character).filter(Character.book_id == book.id).all()
    rules, style_refs = style_anchor(book)
    who = " and ".join(c.name for c in chars) or "the main character"
    description = f"{who} together in a typical scene of the book, full page coloring scene"
    prompt = build_image_prompt(book, "scene", description, chars, [])
    refs = style_refs + [img for c in chars for img in sheet_images(c, 1)]
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    meta = dict(book.meta or {})
    sample = dict(meta.get("sample") or {})
    attempt = int(sample.get("attempts", 0)) + 1
    with usage_context(book_id=book.id, purpose="sample"):
        data = provider.generate(prompt, image_size_hint(book), reference_images=refs[:4], seed=500 + attempt)
    from .cleanup import clean_line_art, save_print_png
    from .specs import page_spec

    spec = page_spec(book.trim_size, book.bleed)
    path = storage.sub(book.id, "sample") / f"sample_{attempt}.png"
    save_print_png(clean_line_art(data, spec), path)
    sample = {"path": storage.rel(path), "status": "pending", "attempts": attempt, "prompt": prompt}
    meta["sample"] = sample
    book.meta = meta
    session.commit()
    return sample


def approve_sample(session: Session, book: Book) -> dict[str, Any]:
    meta = dict(book.meta or {})
    sample = dict(meta.get("sample") or {})
    if not sample.get("path"):
        raise GateError("generate a sample page first")
    sample["status"] = "approved"
    meta["sample"] = sample
    book.meta = meta
    if book.status in ("draft", "analyzed", "themed", "characters"):
        book.status = "characters"
    session.commit()
    return sample


def gates_status(session: Session, book: Book) -> dict[str, Any]:
    chars = session.query(Character).filter(Character.book_id == book.id).all()
    sample = (book.meta or {}).get("sample") or {}
    return {
        "characters_total": len(chars),
        "characters_approved": sum(1 for c in chars if c.status == "approved"),
        "characters_ok": all(c.status == "approved" for c in chars),
        "sample_ok": sample.get("status") == "approved",
    }


# ---------------------------------------------------------------- library


def save_to_library(session: Session, c: Character) -> Character:
    if c.status != "approved":
        raise GateError("only approved characters can be saved to the library")
    c.in_library = True
    session.commit()
    return c


def library(session: Session) -> list[Character]:
    return session.query(Character).filter(Character.in_library.is_(True)).order_by(Character.id.desc()).all()


def reuse_in_book(session: Session, book: Book, lib_char: Character) -> Character:
    """Copy a library character (and its files) into another book, approved."""
    if not lib_char.in_library:
        raise GateError("character is not in the library")
    new = Character(book_id=book.id, name=lib_char.name, species=lib_char.species, personality=lib_char.personality,
                    signature_feature=lib_char.signature_feature, proportions=lib_char.proportions,
                    brief={**(lib_char.brief or {}), "library_source_id": lib_char.id}, status="approved",
                    in_library=False)
    session.add(new)
    session.flush()
    dest = storage.characters_dir(book.id) / str(new.id)
    dest.mkdir(parents=True, exist_ok=True)
    for a in lib_char.assets:
        src = storage.abs_path(a.path)
        if src is None or not src.is_file():
            continue
        target = dest / src.name
        shutil.copy2(src, target)
        new.assets.append(CharacterAsset(kind=a.kind, path=storage.rel(target), selected=a.selected, meta=dict(a.meta or {})))
    if not (book.style_anchor or {}).get("reference_path"):
        sel = selected_asset(new)
        if sel:
            set_style_anchor(session, book, reference_path=sel.path)
    if book.status in ("draft", "analyzed", "themed"):
        book.status = "characters"
    session.commit()
    return new
