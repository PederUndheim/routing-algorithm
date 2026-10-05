import { useRef } from "react";
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from "react";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";

import { COLORS, PANEL_MAX_WIDTH, PANEL_MIN_WIDTH } from "../theme";

/** How far one arrow key moves the edge. Shift multiplies it. */
const STEP = 16;
const BIG_STEP = 64;

type ResizeHandleProps = {
  width: number;
  onWidthChange: (width: number) => void;
  onReset: () => void;
  onCollapse: () => void;
};

/** The drawer's right edge: drag it to resize, double-click to put it back,
 *  or press the tab on it to collapse the drawer.
 *
 * Pointer events with capture rather than window-level mouse listeners: the
 * drag keeps working over the map and outside the window, touch and pen work
 * the same as a mouse, and the browser ends the capture for us if the gesture
 * is interrupted. The handle is also a real separator, so the edge can be
 * moved with the arrow keys without a mouse at all. */
const ResizeHandle = ({ width, onWidthChange, onReset, onCollapse }: ResizeHandleProps) => {
  const dragging = useRef(false);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    // Only the primary button, and never the collapse tab's own clicks.
    if (e.button !== 0) return;
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const stop = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    e.currentTarget.releasePointerCapture(e.pointerId);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? BIG_STEP : STEP;
    if (e.key === "ArrowLeft") onWidthChange(width - step);
    else if (e.key === "ArrowRight") onWidthChange(width + step);
    else if (e.key === "Home") onReset();
    else return;
    e.preventDefault();
  };

  return (
    <Box
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the routing panel"
      aria-valuenow={width}
      aria-valuemin={PANEL_MIN_WIDTH}
      aria-valuemax={PANEL_MAX_WIDTH}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={(e) => {
        if (dragging.current) onWidthChange(e.clientX);
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      sx={{
        position: "absolute",
        top: 0,
        right: -5,
        width: 10,
        height: "100%",
        cursor: "col-resize",
        zIndex: 1400,
        touchAction: "none",
        "&:hover, &:focus-visible": { backgroundColor: "rgba(0,0,0,0.16)" },
        "&:focus-visible": { outline: `2px solid ${COLORS.teal}`, outlineOffset: -1 },
      }}
    >
      <Tooltip title="Collapse" placement="right">
        <IconButton
          aria-label="Collapse the routing panel"
          size="small"
          // The drag starts on pointerdown, so the tab has to keep its own
          // press to itself or every click on it would also be a resize.
          onPointerDown={(e) => e.stopPropagation()}
          onDoubleClick={(e) => e.stopPropagation()}
          onClick={onCollapse}
          sx={{
            position: "absolute",
            top: "50%",
            right: -6,
            transform: "translateY(-50%)",
            width: 20,
            height: 40,
            borderRadius: 2,
            backgroundColor: COLORS.panel,
            zIndex: 1500,
            "&:hover": {
              backgroundColor: "#777777",
              boxShadow: "0 0 5px rgba(0,0,0,0.3)",
            },
          }}
        >
          <ChevronLeftIcon sx={{ color: "white", fontSize: 30 }} />
        </IconButton>
      </Tooltip>
    </Box>
  );
};

export default ResizeHandle;
