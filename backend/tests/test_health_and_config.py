from app.config import get_settings


def test_settings_use_isolated_data_dir(isolated_env):
    s = get_settings()
    assert str(s.data_dir).startswith(str(isolated_env))
    assert s.image_provider == "mock"
    assert s.books_dir.is_dir()
