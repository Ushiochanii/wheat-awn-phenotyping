from awnphen.cli import build_parser, _runtime_check


def test_setup_command_exists():
    help_text = build_parser().format_help()
    assert "setup" in help_text


def test_runtime_check_without_download_is_ready():
    missing, weights = _runtime_check(download_model=False)
    assert missing == []
    assert weights is None


def test_studio_parser_accepts_launch_controls():
    args = build_parser().parse_args(
        ["studio", "--device", "cpu", "--port", "8899", "--no-browser"]
    )
    assert args.device == "cpu"
    assert args.port == 8899
    assert args.no_browser is True


def test_studio_defaults_to_automatic_device_selection():
    args = build_parser().parse_args(["studio"])
    assert args.device == "auto"
