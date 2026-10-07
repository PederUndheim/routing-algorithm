import { useEffect, useRef } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import AddLocationAltOutlinedIcon from "@mui/icons-material/AddLocationAltOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import WarningIcon from "@mui/icons-material/Warning";

import { assess, categoryLabel, questionsFor, ruleText } from "../crux/assessment";
import type { CruxStatus } from "../crux/assessment";
import { cruxBadge, cruxTitle, dangerIcons } from "../dangerClasses";
import { km } from "../format";
import type { CruxEntry, Factor } from "../types";
import { COLORS, CRUX_COLORS, dangerColor } from "../theme";
import CollapseToggle from "./CollapseToggle";
import { outlinedSx, scrollbarSx } from "./styles";

const STATUS_TEXT: Record<CruxStatus, string> = {
  unassessed: "Not assessed yet",
  kept: "Kept - not critical",
  critical: "Critical",
  dismissed: "Dismissed - not relevant",
};

const YesNo = ({
  value,
  onChange,
}: {
  value: boolean | undefined;
  onChange: (value: boolean | undefined) => void;
}) => (
  <ToggleButtonGroup
    exclusive
    size="small"
    value={value === undefined ? null : value ? "yes" : "no"}
    // Pressing the chosen answer again takes it back.
    onChange={(_, next: "yes" | "no" | null) =>
      onChange(next === null ? undefined : next === "yes")
    }
    sx={{
      flexShrink: 0,
      "& .MuiToggleButton-root": {
        px: 1,
        py: 0.25,
        fontSize: 11,
        color: "rgba(255,255,255,0.75)",
        borderColor: "rgba(255,255,255,0.25)",
      },
      "& .MuiToggleButton-root.Mui-selected": { color: "white", borderColor: COLORS.teal },
      "& .MuiToggleButton-root.Mui-selected[value=yes]": {
        backgroundColor: "rgba(211,47,47,0.75)",
        "&:hover": { backgroundColor: "rgba(211,47,47,0.75)" },
      },
      "& .MuiToggleButton-root.Mui-selected[value=no]": {
        backgroundColor: COLORS.teal,
        "&:hover": { backgroundColor: COLORS.teal },
      },
    }}
  >
    <ToggleButton value="yes">Yes</ToggleButton>
    <ToggleButton value="no">No</ToggleButton>
  </ToggleButtonGroup>
);

type AssessmentProps = {
  crux: CruxEntry;
  status: CruxStatus;
  onAnswer: (factor: Factor, value: boolean | undefined) => void;
  onRemove: () => void;
};

/** Under an opened Crux: the questions for its slope category, what the
 *  answers make it, and - for one placed by hand - a way to remove it. */
const Assessment = ({ crux, status, onAnswer, onRemove }: AssessmentProps) => (
  <Box
    sx={{
      mx: 0.5,
      mb: 0.5,
      px: 1.25,
      py: 1,
      borderRadius: "0 0 8px 8px",
      backgroundColor: "rgba(0,0,0,0.18)",
      border: "1px solid rgba(255,255,255,0.10)",
      borderTop: "none",
    }}
  >
    {crux.description && (
      <Typography sx={{ fontSize: 12, color: "white", fontStyle: "italic", mb: 0.75 }}>
        {crux.description}
      </Typography>
    )}

    <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.75)", mb: 1 }}>
      Slope {categoryLabel(crux.category)} · {ruleText(crux.category)}
    </Typography>

    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {questionsFor(crux.category).map((q) => (
        <Box key={q.factor} sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: 12, color: "white", fontWeight: 600 }}>
              {q.title}
            </Typography>
            <Typography sx={{ fontSize: 11.5, color: "rgba(255,255,255,0.75)" }}>
              {q.text}
            </Typography>
          </Box>
          <YesNo value={crux.answers[q.factor]} onChange={(v) => onAnswer(q.factor, v)} />
        </Box>
      ))}
    </Box>

    <Box sx={{ display: "flex", alignItems: "center", mt: 1.25 }}>
      <Typography
        sx={{
          flex: 1,
          fontSize: 12,
          fontWeight: 600,
          color: status === "critical" ? "#FF6B6B" : "rgba(255,255,255,0.85)",
        }}
      >
        {STATUS_TEXT[status]}
      </Typography>
      {crux.source === "manual" && (
        <Button
          size="small"
          onClick={onRemove}
          sx={{ fontSize: 11, color: "rgba(255,255,255,0.75)", minWidth: 0 }}
        >
          Remove crux
        </Button>
      )}
    </Box>
  </Box>
);

const StatusIcon = ({ status }: { status: CruxStatus }) => {
  if (status === "critical") {
    return <WarningIcon titleAccess="Critical" sx={{ color: "#FF6B6B", fontSize: 18 }} />;
  }
  if (status === "kept") {
    return (
      <CheckCircleOutlineIcon
        titleAccess="Assessed, kept"
        sx={{ color: "rgba(255,255,255,0.6)", fontSize: 16 }}
      />
    );
  }
  return null;
};

type CruxRowProps = {
  crux: CruxEntry;
  status: CruxStatus;
  open: boolean;
  onClick: () => void;
};

const CruxRow = ({ crux, status, open, onClick }: CruxRowProps) => {
  const icons = dangerIcons(crux);
  const badge = cruxBadge(crux);
  return (
    <ButtonBase
      onClick={onClick}
      aria-expanded={open}
      sx={{
        width: "100%",
        justifyContent: "flex-start",
        gap: 1,
        px: 1,
        py: 0.5,
        borderRadius: open ? "8px 8px 0 0" : 1.5,
        background: open ? "rgba(54,126,152,0.35)" : "rgba(255,255,255,0.06)",
        outline: status === "critical" ? "1px solid rgba(255,107,107,0.8)" : "none",
        "&:hover": { background: open ? "rgba(54,126,152,0.45)" : "rgba(255,255,255,0.12)" },
      }}
    >
      <Box
        sx={{
          minWidth: 22,
          height: 22,
          px: 0.5,
          boxSizing: "border-box",
          borderRadius: 11,
          backgroundColor: dangerColor(crux),
          color: "white",
          fontSize: 12,
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {crux.number}
      </Box>
      {icons.map((AreaIcon, i) => (
        <AreaIcon key={i} sx={{ color: "white", fontSize: 18 }} />
      ))}
      <Typography
        sx={{
          color: "white",
          fontSize: 13,
          flex: 1,
          minWidth: 0,
          textAlign: "left",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {cruxTitle(crux)}
        {badge && (
          <Box component="span" sx={{ ml: 0.75, color: CRUX_COLORS.steep }}>
            {badge}
          </Box>
        )}
        {crux.source === "manual" && (
          <Box component="span" sx={{ ml: 0.75, color: "rgba(255,255,255,0.55)", fontSize: 11 }}>
            by hand
          </Box>
        )}
      </Typography>
      <StatusIcon status={status} />
      <Typography
        sx={{
          color: "rgba(255,255,255,0.75)",
          fontSize: 12,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {km(crux.distance_m)}
      </Typography>
    </ButtonBase>
  );
};

type CruxListProps = {
  cruxes: readonly CruxEntry[];
  /** The route has been through the identifier, so an empty list means it
   *  found nothing rather than that it has not been asked. */
  analysed: boolean;
  activeId: string | null;
  onActivate: (crux: CruxEntry) => void;
  onAnswer: (cruxId: string, factor: Factor, value: boolean | undefined) => void;
  onRestore: (cruxId: string) => void;
  onRemove: (cruxId: string) => void;
  open: boolean;
  onToggle: () => void;
  placing: boolean;
  onPlace: () => void;
};

/** The Selected route's Cruxes in route order, numbered like their markers.
 *  Clicking one takes the map there and opens its questions. Dismissed ones
 *  wait at the bottom to be restored. Can be folded away to its heading;
 *  the markers on the map stay either way. */
const CruxList = ({
  cruxes,
  analysed,
  activeId,
  onActivate,
  onAnswer,
  onRestore,
  onRemove,
  open,
  onToggle,
  placing,
  onPlace,
}: CruxListProps) => {
  const withStatus = cruxes.map((crux) => ({ crux, status: assess(crux.category, crux.answers) }));
  const current = withStatus.filter((c) => c.status !== "dismissed");
  const dismissed = withStatus.filter((c) => c.status === "dismissed");

  // Opened from the map, the Crux may be scrolled out of sight in here.
  const activeRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  return (
    <Box sx={{ flex: open ? 1 : "none", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: open ? 0.75 : 0 }}>
        <Typography sx={{ color: "white", fontSize: 14, fontWeight: 600 }}>
          Cruxes ({current.length})
        </Typography>
        <CollapseToggle open={open} onToggle={onToggle} what="the list of cruxes" />

        <Box sx={{ flex: 1 }} />

        {/* Pressed again while placing, it gives up. */}
        <Button
          variant="outlined"
          size="small"
          onClick={onPlace}
          startIcon={<AddLocationAltOutlinedIcon />}
          sx={{
            ...outlinedSx,
            fontSize: 12,
            py: 0.1,
            ...(placing && { backgroundColor: "rgba(54,126,152,0.35)" }),
          }}
        >
          {placing ? "Cancel" : "Add crux"}
        </Button>
      </Box>

      {placing && (
        <Typography sx={{ fontSize: 12, color: COLORS.orange, mb: 0.75 }}>
          Click on the map - the crux goes on the nearest point of the route.
        </Typography>
      )}

      {open && cruxes.length === 0 && (
        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
          {analysed
            ? "No Danger class along the analysed part of this route."
            : "None yet. Press Identify cruxes, or add one by hand."}
        </Typography>
      )}

      {/* Takes whatever height the drawer has left and scrolls inside it, so
          a long tour does not stretch the drawer into a scroll of its own. */}
      {open && cruxes.length > 0 && (
        <Box
          component="ol"
          sx={{
            listStyle: "none",
            p: "1px",
            m: 0,
            display: "flex",
            flexDirection: "column",
            gap: 0.5,
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            ...scrollbarSx,
          }}
        >
          {current.map(({ crux, status }) => {
            const active = crux.id === activeId;
            return (
              <Box component="li" key={crux.id} ref={active ? activeRef : undefined}>
                <CruxRow crux={crux} status={status} open={active} onClick={() => onActivate(crux)} />
                {active && (
                  <Assessment
                    crux={crux}
                    status={status}
                    onAnswer={(factor, value) => onAnswer(crux.id, factor, value)}
                    onRemove={() => onRemove(crux.id)}
                  />
                )}
              </Box>
            );
          })}

          {dismissed.length > 0 && (
            <Box component="li" sx={{ mt: 1 }}>
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.6)", mb: 0.5 }}>
                Dismissed ({dismissed.length})
              </Typography>
              {dismissed.map(({ crux }) => (
                <Box
                  key={crux.id}
                  sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.25, opacity: 0.6 }}
                >
                  <Typography
                    sx={{
                      flex: 1,
                      fontSize: 12,
                      color: "white",
                      textDecoration: "line-through",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {crux.number}. {cruxTitle(crux)} · {km(crux.distance_m)}
                  </Typography>
                  <Button
                    size="small"
                    onClick={() => onRestore(crux.id)}
                    sx={{ fontSize: 11, color: "white", minWidth: 0, py: 0 }}
                  >
                    Restore
                  </Button>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
};

export default CruxList;
