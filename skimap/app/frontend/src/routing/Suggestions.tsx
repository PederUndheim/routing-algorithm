import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import CloseIcon from "@mui/icons-material/Close";

import { km, stretchLength } from "../format";
import type { RouteSuggestion } from "../routes/suggestions";
import { verdictOf } from "../routes/suggestions";
import type { GroundSummary } from "../types";
import { COLORS } from "../theme";
import { accentOutlinedSx, fittedButtonSx, fittedLabelSx, hintSx, outlinedSx } from "./styles";

/** The rows a suggestion is judged on: always steep ground and length, the
 *  rest only where either side has any. */
const ROWS: { key: keyof GroundSummary; label: string; always?: boolean }[] = [
  { key: "steep_m", label: "Steep slope", always: true },
  { key: "release_m", label: "Release area" },
  { key: "fall_m", label: "Fall hazard" },
  { key: "runout_m", label: "Runout area" },
  { key: "no_data_m", label: "No data" },
];

/** Which suggestions the drawer and map show: all of them, or only those
 *  that take the line off danger - the rest only make the going easier by
 *  the cost surface, or even put it on more steep ground. */
export const shownSuggestions = (
  suggestions: readonly RouteSuggestion[],
  onlySafer: boolean
): RouteSuggestion[] =>
  onlySafer ? suggestions.filter((s) => verdictOf(s) === "safer") : [...suggestions];

const Change = ({ label, before, after }: { label: string; before: number; after: number }) => {
  const better = after < before - 0.5;
  const worse = after > before + 0.5;
  return (
    <Box sx={{ display: "flex", fontSize: 12, color: "rgba(255,255,255,0.85)" }}>
      <Box component="span" sx={{ flex: 1 }}>
        {label}
      </Box>
      <Box component="span" sx={{ fontVariantNumeric: "tabular-nums" }}>
        {stretchLength(before)} →{" "}
        <Box
          component="span"
          sx={{
            fontWeight: better || worse ? 600 : 400,
            color: better ? "#7CD992" : worse ? "#FF8A80" : "inherit",
          }}
        >
          {stretchLength(after)}
        </Box>
      </Box>
    </Box>
  );
};

type CardProps = {
  suggestion: RouteSuggestion;
  number: number;
  active: boolean;
  onActivate: () => void;
  onAccept: () => void;
  onReject: () => void;
};

const SuggestionCard = ({ suggestion: s, number, active, onActivate, onAccept, onReject }: CardProps) => {
  const lengthChange = s.after.length_m - s.before.length_m;
  return (
    <Box
      onClick={onActivate}
      sx={{
        p: 1.25,
        borderRadius: 2,
        cursor: "pointer",
        backgroundColor: active ? "rgba(54,126,152,0.30)" : "rgba(0,0,0,0.18)",
        border: `1px solid ${active ? COLORS.teal : "rgba(255,255,255,0.10)"}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
        <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, flex: 1 }}>
          {number}. {km(s.startM)} – {km(s.endM)}
        </Typography>
        {s.minor && (
          <Typography
            title="A smaller improvement, shown because the line has few big ones"
            sx={{ fontSize: 11, color: "rgba(255,255,255,0.6)" }}
          >
            small
          </Typography>
        )}
      </Box>

      {ROWS.filter((row) => row.always || s.before[row.key] > 0 || s.after[row.key] > 0).map(
        (row) => (
          <Change
            key={row.key}
            label={row.label}
            before={s.before[row.key]}
            after={s.after[row.key]}
          />
        )
      )}
      <Box sx={{ display: "flex", fontSize: 12, color: "rgba(255,255,255,0.85)" }}>
        <Box component="span" sx={{ flex: 1 }}>
          Length
        </Box>
        <Box component="span" sx={{ fontVariantNumeric: "tabular-nums" }}>
          {stretchLength(s.before.length_m)} → {stretchLength(s.after.length_m)} (
          {lengthChange >= 0 ? "+" : "−"}
          {stretchLength(Math.abs(lengthChange))})
        </Box>
      </Box>

      <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
        <Button
          variant="outlined"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onReject();
          }}
          sx={{ ...outlinedSx, flex: 1, fontSize: 12 }}
        >
          Keep my line
        </Button>
        <Button
          variant="outlined"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onAccept();
          }}
          sx={{ ...accentOutlinedSx, flex: 1, fontSize: 12 }}
        >
          Use this way
        </Button>
      </Box>
    </Box>
  );
};

/** Optimise route: looks for the suggestions, and again on a line that
 *  already has some. Apart from the list it fills, so it can sit beside
 *  Make corridor. */
export const OptimiseButton = ({
  isSearching,
  onSearch,
}: {
  isSearching: boolean;
  onSearch: () => void;
}) => (
  <Button
    variant="outlined"
    fullWidth
    size="small"
    disabled={isSearching}
    onClick={onSearch}
    startIcon={isSearching ? <CircularProgress size={14} color="inherit" /> : <AltRouteIcon />}
    sx={{ ...outlinedSx, ...fittedButtonSx, fontSize: 12 }}
  >
    <Box component="span" sx={fittedLabelSx}>
      {isSearching ? "Optimising..." : "Optimise route"}
    </Box>
  </Button>
);

export type SuggestionsProps = {
  /** Absent until looked for; see Route.suggestions. */
  suggestions: readonly RouteSuggestion[] | undefined;
  isSearching: boolean;
  onSearch: () => void;
  onlySafer: boolean;
  onOnlySaferChange: (only: boolean) => void;
  activeId: string | null;
  onActivate: (suggestion: RouteSuggestion) => void;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onAcceptAll: (ids: string[]) => void;
  onDismiss: () => void;
};

/** What Optimise route found, for a line the router did not make: where a
 *  clearly cheaper way runs close beside it, one card each, to take or
 *  leave. The line is never routed again - every suggestion leaves it and
 *  rejoins it, and taking one is an edit of that stretch alone. Nothing
 *  until it has been looked for, and nothing while it is being looked for
 *  again. */
const Suggestions = ({
  suggestions,
  isSearching,
  onlySafer,
  onOnlySaferChange,
  activeId,
  onActivate,
  onAccept,
  onReject,
  onAcceptAll,
  onDismiss,
}: SuggestionsProps) => {
  if (suggestions === undefined || isSearching) return null;

  const shown = shownSuggestions(suggestions, onlySafer);
  const hidden = suggestions.length - shown.length;

  return (
    <Box
      sx={{
        p: 1.25,
        borderRadius: 2,
        border: "1px solid rgba(255,255,255,0.15)",
        display: "flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center" }}>
        <Typography sx={{ color: "white", fontSize: 14, fontWeight: 600, flex: 1 }}>
          Suggested changes
        </Typography>
        <IconButton size="small" aria-label="Close suggestions" onClick={onDismiss}>
          <CloseIcon sx={{ color: "white", fontSize: 18 }} />
        </IconButton>
      </Box>

      <Typography sx={hintSx}>
        Ways close beside your line that the cost surface finds clearly better. Each one is
        yours to take or leave - the rest of the line stays as it is.
      </Typography>

      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={onlySafer}
            onChange={(e) => onOnlySaferChange(e.target.checked)}
            sx={{
              "& .MuiSwitch-switchBase.Mui-checked": { color: COLORS.teal },
              "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
                backgroundColor: COLORS.teal,
              },
            }}
          />
        }
        label="Only ways off steep ground"
        sx={{ color: "white", mr: 0, "& .MuiFormControlLabel-label": { fontSize: 12 } }}
      />

      {shown.length === 0 && (
        <Typography sx={hintSx}>
          {suggestions.length === 0
            ? "No clearly better way close to this line."
            : `None that take the line off steep ground. ${hidden} only change the going - turn the switch off to see ${hidden === 1 ? "it" : "them"}.`}
        </Typography>
      )}

      {shown.map((s, i) => (
        <SuggestionCard
          key={s.id}
          suggestion={s}
          number={i + 1}
          active={s.id === activeId}
          onActivate={() => onActivate(s)}
          onAccept={() => onAccept(s.id)}
          onReject={() => onReject(s.id)}
        />
      ))}

      {shown.length > 0 && hidden > 0 && (
        <Typography sx={hintSx}>
          {hidden} more only change the going, not the danger.
        </Typography>
      )}

      {shown.length > 1 && (
        <Button
          variant="outlined"
          size="small"
          onClick={() => onAcceptAll(shown.map((s) => s.id))}
          sx={{ ...accentOutlinedSx, fontSize: 12 }}
        >
          Use all {shown.length} shown
        </Button>
      )}
    </Box>
  );
};

export default Suggestions;
