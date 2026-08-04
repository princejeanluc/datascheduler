"""
DataScheduler — tests/test_logging_setup.py
Vérifie que main.py::_configure_logging() écrit bien dans un fichier journalier avec rotation
(chantier UX post-personas, item 3 couche 1 — persona "Nadia", persona "Marc") — avant ce
correctif, le logging applicatif était console uniquement (StreamHandler par défaut de
logging.basicConfig), perdu à la fermeture de l'app. Toujours appelé avec un répertoire injecté :
importer main.py ne doit jamais, en soi, écrire dans le vrai %APPDATA% de la machine — seul un
appel explicite à main() (le vrai lancement de l'app) le fait.
"""

import logging

import main


def _fresh_logger(name: str) -> logging.Logger:
    """Un logger dédié par test, jamais mis en cache entre les tests."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger


def test_configure_logging_creates_log_directory(tmp_path):
    log_dir = tmp_path / "logs"
    assert not log_dir.exists()
    main._configure_logging(log_dir)
    assert log_dir.exists()


def test_configure_logging_writes_to_file(tmp_path):
    log_dir = tmp_path / "logs"
    main._configure_logging(log_dir)

    logger = _fresh_logger("test.logging_setup.write")
    logger.info("message de test unique 12345")

    log_file = log_dir / "app.log"
    assert log_file.exists()
    assert "message de test unique 12345" in log_file.read_text(encoding="utf-8")


def test_configure_logging_uses_rotating_file_handler(tmp_path):
    log_dir = tmp_path / "logs"
    main._configure_logging(log_dir)

    from logging.handlers import RotatingFileHandler
    handlers = logging.getLogger().handlers
    file_handlers = [h for h in handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) >= 1
    assert file_handlers[-1].maxBytes > 0
    assert file_handlers[-1].backupCount >= 1


def test_default_log_dir_is_under_appdata_datascheduler(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    log_dir = main._default_log_dir()
    assert log_dir == tmp_path / "DataScheduler" / "logs"
