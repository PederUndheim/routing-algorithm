import { useState } from "react";
import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import InsightsIcon from "@mui/icons-material/Insights";

import { CORRIDOR_WIDTH_LABELS, CORRIDOR_WIDTHS } from "../corridorWidths";
import { km } from "../format";
import type { Route } from "../routes/routeList";
import type { CorridorWidth, CruxEntry, CruxNote, Factor, Rating } from "../types";
import { COLORS } from "../theme";
import CruxList from "./CruxList";
import { fittedButtonSx, fittedLabelSx, outlinedSx } from "./styles";

type CorridorControlsProps = {
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorOpacity: number;
  onCorridorOpacityChange: (opacity: number) => void;
  corridorWidth: CorridorWidth;
  onCorridorWidthChange: (width: CorridorWidth) => void;
  /** False for a corridor that came with the standard band alone. */
  widthsAvailable: boolean;
};

/** A Route's corridor: on or off, how wide, and how strong. Compact - it
 *  is a setting, not something to read. */
export const CorridorControls = ({
  showCorridor,
  onShowCorridorChange,
  corridorOpacity,
  onCorridorOpacityChange,
  corridorWidth,
  onCorridorWidthChange,
  widthsAvailable,
}: CorridorControlsProps) => (
  <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 1 }}>
    <FormControlLabel
      control={
        <Switch
          size="small"
          checked={showCorridor}
          onChange={(e) => onShowCorridorChange(e.target.checked)}
          sx={{
            "& .MuiSwitch-switchBase.Mui-checked": { color: COLORS.teal },
            "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
              backgroundColor: COLORS.teal,
            },
          }}
        />
      }
      label="Show corridor"
      sx={{
        color: "white",
        mr: 0,
        whiteSpace: "nowrap",
        "& .MuiFormControlLabel-label": { fontSize: 13 },
      }}
    />

    {/* Kept in the layout but dimmed when the corridor is off, so the
        panel does not jump as you toggle it - same as the map overlays. */}
    <Box
      sx={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        pl: 1.5,
        pr: 0.5,
        opacity: showCorridor ? 1 : 0.45,
        pointerEvents: showCorridor ? "auto" : "none",
        transition: "opacity 0.15s ease",
      }}
    >
      {/* Centred in whatever room the drawer's width leaves between the
          switch and the opacity slider, which keeps its own size. */}
      <Box sx={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "center" }}>
        <WidthSlider
          width={corridorWidth}
          onChange={onCorridorWidthChange}
          disabled={!showCorridor || !widthsAvailable}
          title={
            widthsAvailable
              ? "How much room around the route the corridor shows"
              : "This corridor was made with one width only - route or make it again for the others"
          }
        />
      </Box>
      {/* Built like WidthSlider - same box, same padding, its readout where
          the step names sit - so the two rails share one line. */}
      {/* The one thing in the row that gives way on a narrow drawer. */}
      <Box
        sx={{
          ...sliderBoxSx,
          flex: `0 1 ${OPACITY_SLIDER_PX}px`,
          minWidth: 44,
          ml: 1,
          position: "relative",
        }}
      >
        <Slider
          value={corridorOpacity}
          min={0}
          max={1}
          step={0.05}
          size="small"
          disabled={!showCorridor}
          onChange={(_, v) => onCorridorOpacityChange(v as number)}
          aria-label="Corridor opacity"
          sx={sliderSx}
        />
        <Typography
          sx={{
            ...sliderLabelSx,
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            top: SLIDER_BOX_PT_PX + SLIDER_LABEL_TOP_PX,
            color: "white",
            fontWeight: 300,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Math.round(corridorOpacity * 100)}%
        </Typography>
      </Box>
    </Box>
  </Box>
);

const WIDTH_SLIDER_PX = 78;
const OPACITY_SLIDER_PX = 84;

// Shared by both sliders in the corridor row, so their rails sit at one
// height and the labels under them on one line.
const SLIDER_BOX_PT_PX = 2;
const SLIDER_LABEL_TOP_PX = 16;
const sliderBoxSx = { flexShrink: 0, pt: `${SLIDER_BOX_PT_PX}px`, pb: 1.75 };
const sliderLabelSx = { fontSize: 10, lineHeight: 1, whiteSpace: "nowrap" };
const sliderSx = {
  color: COLORS.teal,
  display: "block",
  py: "6px",
  "&.Mui-disabled": { color: "rgba(255,255,255,0.5)" },
  "& .MuiSlider-thumb": { width: 12, height: 12 },
};

/** Narrow, normal or wide, as three stops on a short slider with the name
 *  of each under it. A slider rather than three buttons because the widths
 *  are steps along one scale, and it reads as such; no track, because no
 *  stop is "more" of the setting than another. */
const WidthSlider = ({
  width,
  onChange,
  disabled,
  title,
}: {
  width: CorridorWidth;
  onChange: (width: CorridorWidth) => void;
  disabled: boolean;
  title: string;
}) => {
  const at = CORRIDOR_WIDTHS.indexOf(width);
  return (
    <Box title={title} sx={{ ...sliderBoxSx, width: WIDTH_SLIDER_PX }}>
      <Slider
        value={at}
        min={0}
        max={CORRIDOR_WIDTHS.length - 1}
        step={1}
        track={false}
        size="small"
        disabled={disabled}
        onChange={(_, v) => onChange(CORRIDOR_WIDTHS[v as number])}
        aria-label="Corridor width"
        getAriaValueText={(v) => CORRIDOR_WIDTH_LABELS[CORRIDOR_WIDTHS[v]]}
        marks={CORRIDOR_WIDTHS.map((w, i) => ({
          value: i,
          label: CORRIDOR_WIDTH_LABELS[w],
        }))}
        sx={{
          ...sliderSx,
          // MUI leaves room under a marked slider for labels at its default
          // size; these are smaller and sit in the row's own padding.
          "&.MuiSlider-marked": { mb: 0 },
          "& .MuiSlider-rail": { opacity: 0.35 },
          "& .MuiSlider-mark": {
            width: 4,
            height: 4,
            borderRadius: "50%",
            backgroundColor: "rgba(255,255,255,0.7)",
          },
          "& .MuiSlider-markLabel": {
            ...sliderLabelSx,
            top: SLIDER_LABEL_TOP_PX,
            color: "rgba(255,255,255,0.6)",
          },
          [`& .MuiSlider-markLabel[data-index="${at}"]`]: { color: "white", fontWeight: 600 },
        }}
      />
    </Box>
  );
};

/** Where CorridorControls go on a Route that has no corridor yet: drawn,
 *  uploaded, or edited since it was made. Outlined, so it does not compete
 *  with Identify cruxes below it, and short, to fit beside Optimise route. */
export const MakeCorridorButton = ({
  isMaking,
  onMake,
}: {
  isMaking: boolean;
  onMake: () => void;
}) => (
  <Button
    variant="outlined"
    fullWidth
    size="small"
    disabled={isMaking}
    onClick={onMake}
    startIcon={isMaking ? <CircularProgress size={14} color="inherit" /> : <InsightsIcon />}
    sx={{ ...outlinedSx, ...fittedButtonSx, fontSize: 12 }}
  >
    <Box component="span" sx={fittedLabelSx}>
      {isMaking ? "Making..." : "Make corridor"}
    </Box>
  </Button>
);

type SelectedRouteProps = {
  route: Route;
  activeCruxId: string | null;
  highlightedCruxId: string | null;
  onActivateCrux: (crux: CruxEntry) => void;
  onAnswer: (cruxId: string, factor: Factor, value: Rating | undefined) => void;
  onOverall: (cruxId: string, value: Rating | undefined) => void;
  onKeep: (cruxId: string, keep: boolean | undefined) => void;
  onNote: (cruxId: string, note: CruxNote, text: string) => void;
  onRestoreCrux: (cruxId: string) => void;
  onDeleteCrux: (cruxId: string) => void;
  onUndeleteCrux: (cruxId: string) => void;
  onEditCrux: (crux: CruxEntry) => void;
  onMoveCrux: (crux: CruxEntry) => void;
  onEditExtent: (crux: CruxEntry) => void;
  placingCrux: boolean;
  placingText: string;
  onPlaceCrux: () => void;
  addCruxForm: ReactNode;
  editingExtent: boolean;
  onFinishExtent: () => void;
  onResetExtent: () => void;
};

/** What the drawer shows for the Selected route below Identify cruxes: the
 *  warning if part of it could not be analysed, and its Cruxes. Highlighted
 *  in the list above, so the name is not repeated here. */
const SelectedRoute = ({
  route,
  activeCruxId,
  highlightedCruxId,
  onActivateCrux,
  onAnswer,
  onOverall,
  onKeep,
  onNote,
  onRestoreCrux,
  onDeleteCrux,
  onUndeleteCrux,
  onEditCrux,
  onMoveCrux,
  onEditExtent,
  placingCrux,
  placingText,
  onPlaceCrux,
  addCruxForm,
  editingExtent,
  onFinishExtent,
  onResetExtent,
}: SelectedRouteProps) => {
  // Here rather than in the list, so it holds across switching routes and
  // a folded list gives its height back to the drawer.
  const [listOpen, setListOpen] = useState(true);

  return (
    <Box
      sx={{
        mt: 1.5,
        display: "flex",
        flexDirection: "column",
        gap: 1,
        // Fills the rest of the drawer, and never shrinks below what it
        // holds - the crux list keeps its height, and the drawer scrolls.
        flex: "1 0 auto",
      }}
    >
      {/* A safety caveat, so always in plain sight. */}
      {route.crux && route.crux.no_data_m > 0 && (
        <Typography
          sx={{
            fontSize: 12,
            color: COLORS.orange,
            p: 1.5,
            borderRadius: 2,
            backgroundColor: "rgba(0,0,0,0.18)",
            border: "1px solid rgba(255,255,255,0.10)",
            flexShrink: 0,
          }}
        >
          {km(route.crux.no_data_m)} of route not analysed: there is no terrain
          data there. It is drawn grey and dashed - do not read it as safe.
        </Typography>
      )}

      {route.unanalysedM !== undefined && (
        <Typography
          sx={{
            fontSize: 12,
            color: COLORS.orange,
            p: 1.5,
            borderRadius: 2,
            backgroundColor: "rgba(0,0,0,0.18)",
            border: "1px solid rgba(255,255,255,0.10)",
            flexShrink: 0,
          }}
        >
          {km(route.unanalysedM)} of route changed since cruxes were identified, and not
          analysed yet. Update cruxes to check it.
        </Typography>
      )}

      <CruxList
        cruxes={route.cruxes}
        analysed={route.crux !== null}
        activeId={activeCruxId}
        highlightedId={highlightedCruxId}
        onActivate={onActivateCrux}
        onAnswer={onAnswer}
        onOverall={onOverall}
        onKeep={onKeep}
        onNote={onNote}
        onRestore={onRestoreCrux}
        onDelete={onDeleteCrux}
        onUndelete={onUndeleteCrux}
        onEdit={onEditCrux}
        onMove={onMoveCrux}
        onEditExtent={onEditExtent}
        open={listOpen}
        onToggle={() => setListOpen((prev) => !prev)}
        placing={placingCrux}
        placingText={placingText}
        onPlace={onPlaceCrux}
        addForm={addCruxForm}
        editingExtent={editingExtent}
        onFinishExtent={onFinishExtent}
        onResetExtent={onResetExtent}
      />
    </Box>
  );
};

export default SelectedRoute;
