"""Terminal-styled screenshot renderer using Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.schemas import ExecutionEvidence, ScreenshotArtifact


class TerminalRenderer:
    """Render execution output as a terminal-styled PNG image."""

    BG_COLOR = (30, 30, 30)
    TEXT_COLOR = (204, 204, 204)
    HEADER_COLOR = (50, 50, 50)
    HEADER_TEXT_COLOR = (180, 180, 180)
    PADDING = 20
    LINE_HEIGHT = 22
    FONT_SIZE = 14

    def render(
        self, evidence: ExecutionEvidence, output_dir: Path
    ) -> ScreenshotArtifact:
        """Render the execution output to a PNG file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stdout = ""
        if evidence.execution_result:
            stdout = evidence.execution_result.stdout or ""

        lines = stdout.split("\n")
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            lines = ["(no output)"]

        # Calculate dimensions
        font = self._get_font()
        # Expand tabs before calculating width
        expanded_lines = [line.expandtabs(4) for line in lines]
        max_width = max(self._text_width(font, line) for line in expanded_lines)
        width = max(max_width + self.PADDING * 2, 400)
        header_height = 30
        content_height = len(lines) * self.LINE_HEIGHT + self.PADDING * 2
        height = max(header_height + content_height, 100)

        # Create image
        img = Image.new("RGB", (width, height), self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Draw header bar
        draw.rectangle([(0, 0), (width, header_height)], fill=self.HEADER_COLOR)
        # Draw terminal dots
        for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            draw.ellipse(
                [(10 + i * 20, 8), (24 + i * 20, 22)],
                fill=color,
            )

        # Draw output text
        y = header_height + self.PADDING
        for line in expanded_lines:
            draw.text((self.PADDING, y), line, fill=self.TEXT_COLOR, font=font)
            y += self.LINE_HEIGHT

        # Save
        image_path = output_dir / f"{evidence.level}_output.png"
        img.save(str(image_path), "PNG")

        return ScreenshotArtifact(
            level=evidence.level,
            image_path=str(image_path),
            width=width,
            height=height,
        )

    def _get_font(self) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get a monospace font, falling back to default."""
        font_names = [
            "consola.ttf",       # Windows Consolas
            "cour.ttf",          # Windows Courier New
            "DejaVuSansMono.ttf",
            "LiberationMono-Regular.ttf",
        ]
        for name in font_names:
            try:
                return ImageFont.truetype(name, self.FONT_SIZE)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _text_width(self, font, text: str) -> int:
        """Calculate the width of rendered text."""
        try:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0] if bbox else len(text) * 8
        except AttributeError:
            return len(text) * 8
