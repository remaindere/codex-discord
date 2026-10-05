import Path
import json
import asyncio
from bot.storage.sessions import SessionStore

def test_session_store_reads_legacy_integer(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "sessions.json"
        path.write_text(
            json.dumps({"user-channel": 7}),
            encoding="utf-8",
        )

        store = SessionStore(path, "default")
        info = await store.get("user-channel")

        assert info.conversation_id == "user-channel-ep7"
        assert info.epoch == 7
        assert info.model == "default"
        assert info.last_route is None

    asyncio.run(scenario())


def test_session_store_reads_existing_dictionary_without_last_route(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        path = tmp_path / "sessions.json"
        path.write_text(
            json.dumps(
                {
                    "user-channel": {
                        "epoch": 3,
                        "model": "custom",
                    }
                }
            ),
            encoding="utf-8",
        )

        store = SessionStore(path, "default")
        info = await store.get("user-channel")

        assert info.conversation_id == "user-channel-ep3"
        assert info.epoch == 3
        assert info.model == "custom"
        assert info.last_route is None

    asyncio.run(scenario())


def test_session_store_persists_last_route(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "sessions.json"
        store = SessionStore(path, "default")

        info = await store.set_last_route("user-channel", "codex")

        assert info.conversation_id == "user-channel-ep1"
        assert info.epoch == 1
        assert info.model == "default"
        assert info.last_route == "codex"

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["user-channel"] == {
            "epoch": 1,
            "model": "default",
            "last_route": "codex",
        }

        loaded = await store.get("user-channel")
        assert loaded.last_route == "codex"

    asyncio.run(scenario())


def test_set_model_preserves_last_route(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SessionStore(tmp_path / "sessions.json", "default")

        await store.set_last_route("user-channel", "codex")
        info = await store.set_model("user-channel", "custom-model")

        assert info.conversation_id == "user-channel-ep1"
        assert info.epoch == 1
        assert info.model == "custom-model"
        assert info.last_route == "codex"

        loaded = await store.get("user-channel")
        assert loaded.model == "custom-model"
        assert loaded.last_route == "codex"

    asyncio.run(scenario())


def test_session_reset_clears_last_route(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SessionStore(tmp_path / "sessions.json", "default")

        await store.set_last_route("user-channel", "codex")
        info = await store.reset("user-channel")

        assert info.conversation_id == "user-channel-ep2"
        assert info.epoch == 2
        assert info.last_route is None

        saved = json.loads(
            (tmp_path / "sessions.json").read_text(encoding="utf-8")
        )
        assert saved["user-channel"]["epoch"] == 2
        assert saved["user-channel"]["last_route"] is None

        loaded = await store.get("user-channel")
        assert loaded.epoch == 2
        assert loaded.last_route is None

    asyncio.run(scenario())
    
def test_session_reset_preserves_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SessionStore(tmp_path / "sessions.json", "default")

        changed = await store.set_model("user-channel", "custom")
        reset = await store.reset("user-channel")

        assert changed.conversation_id == "user-channel-ep1"
        assert reset.conversation_id == "user-channel-ep2"
        assert reset.model == "custom"
        assert reset.last_route is None

    asyncio.run(scenario())