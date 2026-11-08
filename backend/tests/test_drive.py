from pathlib import Path

from app.services import drive


def test_folder_naming():
    assert drive.sanitize_folder_name('My/Book: "Best"?') == "My Book Best"
    assert drive.sanitize_folder_name("   ") == "Untitled book"
    assert drive.unique_folder_name("Garden", set()) == "Garden"
    assert drive.unique_folder_name("Garden", {"Garden"}) == "Garden (2)"
    assert drive.unique_folder_name("Garden", {"Garden", "Garden (2)"}) == "Garden (3)"
    assert drive.sanitize_folder_name("حديقة الأصدقاء") == "حديقة الأصدقاء"


def _export(tmp_path: Path) -> Path:
    d = tmp_path / "export"
    (d / "pages").mkdir(parents=True)
    (d / "interior.pdf").write_bytes(b"%PDF-1")
    (d / "cover.pdf").write_bytes(b"%PDF-2")
    (d / "book-settings.json").write_text("{}")
    for i in range(3):
        (d / "pages" / f"{i:03d}.png").write_bytes(b"x" * (i + 1))
    return d


def test_plan_uploads_skips_existing_same_size(tmp_path):
    d = _export(tmp_path)
    todo, skipped = drive.plan_uploads(d, {"": {"interior.pdf": 6}, "pages": {"000.png": 1, "001.png": 999}})
    assert {i.remote_name for i in skipped} == {"interior.pdf", "000.png"}
    assert len(todo) == 4


class FakeDrive:
    def __init__(self):
        self.folders = {"root": {"Garden Friends": "f0"}}
        self.files: dict[str, dict[str, int]] = {}
        self.n = 0
        self.uploads = []

    def list_folder_names(self, parent):
        return set(self.folders.get(parent or "root", {}))

    def find_folder(self, name, parent):
        return self.folders.get(parent or "root", {}).get(name)

    def create_folder(self, name, parent):
        self.n += 1
        fid = f"id{self.n}"
        self.folders.setdefault(parent or "root", {})[name] = fid
        return fid

    def list_files(self, folder_id):
        return dict(self.files.get(folder_id, {}))

    def upload(self, local, name, folder_id):
        self.uploads.append((folder_id, name))
        self.files.setdefault(folder_id, {})[name] = local.stat().st_size
        return "x"

    def folder_link(self, folder_id):
        return f"https://drive/{folder_id}"


def test_upload_export_creates_unique_folder_and_resumes(tmp_path):
    d = _export(tmp_path)
    fake = FakeDrive()
    res = drive.upload_export(fake, "Garden Friends", d)
    assert res["folder_name"] == "Garden Friends (2)" and res["uploaded"] == 6 and res["skipped"] == 0
    assert ("id2", "000.png") in fake.uploads  # pages subfolder
    res2 = drive.upload_export(fake, "Garden Friends (2)", d, resume_folder_id=res["folder_id"])
    assert res2["uploaded"] == 0 and res2["skipped"] == 6


def test_token_file_permissions(isolated_env):
    drive.save_token('{"token": "x"}')
    mode = drive.token_path().stat().st_mode & 0o777
    assert mode == 0o600
    assert drive.is_connected()
    drive.disconnect()
    assert not drive.is_connected()
