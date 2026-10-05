from bot.message_splitter import split_discord_message


def test_prefers_paragraph_boundaries() -> None:
    text = ("a" * 80) + "\n\n" + ("b" * 80)
    chunks = split_discord_message(text, limit=100)
    assert chunks == ["a" * 80, "b" * 80]


def test_empty_message() -> None:
    assert split_discord_message("") == []
