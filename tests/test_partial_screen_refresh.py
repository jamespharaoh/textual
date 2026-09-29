"""A partial screen refresh must retain other widgets' pending repaints."""

import asyncio

import pytest
from rich.segment import Segment
from rich.style import Style

from textual._compositor import ChopsUpdate
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.geometry import Region, Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import Static


class NumberedReader(ScrollView):
    def on_mount(self) -> None:
        self.virtual_size = Size(128, 500)

    def render_line(self, y: int) -> Strip:
        number = y + self.scroll_offset.y
        text = f"[{number:04d}]" + "x" * 120
        width = self.scrollable_content_region.width
        return (
            Strip([Segment(text, Style())])
            .crop(0, width)
            .extend_cell_length(width, Style())
        )


class ReaderApp(App):
    CSS = """
    Screen { align: center middle; }
    #dialog { width: 96%; height: 92%; border: heavy $primary;
        background: $surface; padding: 1 2; }
    NumberedReader { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("reader")
            yield NumberedReader()


@pytest.mark.parametrize("full_rows", [False, True])
def test_partial_screen_refresh_preserves_pending_widget_repaint(
    full_rows: bool,
) -> None:
    asyncio.run(_check_partial_screen_refresh(full_rows))


async def _check_partial_screen_refresh(
    full_rows: bool,
) -> None:
    app = ReaderApp()
    updates = []
    # Pilot does not expose partial compositor updates, so record them here.
    app._display = lambda _screen, update: updates.append(update)

    async with app.run_test(size=(120, 50)) as pilot:
        reader = app.screen.query_one(NumberedReader)
        reader.scroll_to(y=4, animate=False, immediate=True)
        await pilot.pause()
        updates.clear()

        # Queue a reader repaint, then refresh the screen before it is painted.
        # The full-row refresh is the control for the narrower region.
        reader.scroll_to(y=0, animate=False, immediate=True)
        region = (
            Region(0, reader.region.y, app.size.width, reader.region.height)
            if full_rows
            else Region(
                2, reader.region.y, app.size.width // 2 - 2, reader.region.height
            )
        )
        reader.call_later(app.screen.refresh, region)
        await pilot.pause()

        spans = [
            span
            for update in updates
            if isinstance(update, ChopsUpdate)
            for span in update.spans
        ]
        assert spans
        content_row = reader.region.y + 1
        assert any(
            y == content_row and x1 <= reader.region.x and x2 >= reader.region.right
            for y, x1, x2 in spans
        )


def test_partial_screen_refresh_preserves_static_widget_repaint() -> None:
    asyncio.run(_check_static_repaint())


async def _check_static_repaint() -> None:
    class StaticApp(App):
        CSS = "#row { width: 100%; }"

        def compose(self) -> ComposeResult:
            yield Static("before", id="row")

    app = StaticApp()
    updates = []
    # Pilot does not expose partial compositor updates, so record them here.
    app._display = lambda _screen, update: updates.append(update)
    async with app.run_test(size=(80, 24)) as pilot:
        row = app.query_one("#row", Static)
        await pilot.pause()
        updates.clear()
        row.refresh()
        app.screen.refresh(Region(0, row.region.y, 5, row.region.height))
        await pilot.pause()

        spans = [
            span
            for update in updates
            if isinstance(update, ChopsUpdate)
            for span in update.spans
        ]
        assert any(
            y == row.region.y and x1 <= row.region.x and x2 >= row.region.right
            for y, x1, x2 in spans
        )
