import { useEffect, useRef, useState } from "react";

import Box from "@mui/material/Box";
import ClickAwayListener from "@mui/material/ClickAwayListener";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddLocationAltOutlinedIcon from "@mui/icons-material/AddLocationAltOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import OpenWithIcon from "@mui/icons-material/OpenWith";
import StraightenIcon from "@mui/icons-material/Straighten";
import ThumbDownIcon from "@mui/icons-material/ThumbDown";
import ThumbUpIcon from "@mui/icons-material/ThumbUp";

import {
  OVERALL_INFO,
  RATINGS,
  hasOwnOverall,
  isDecided,
  questionsFor,
  ratingOf,
  shelfOf,
  verdictOf,
} from "../crux/assessment";
import type { RatingInfo } from "../crux/assessment";
import { cruxBadge, cruxTitle, dangerIcons } from "../dangerClasses";
import { km } from "../format";
import type { CruxEntry, Factor, Rating } from "../types";
import { COLORS, dangerColor, lighten } from "../theme";
import RatingMark, { VerdictDisc } from "../ui/RatingMark";
import CollapseToggle from "./CollapseToggle";
import { outlinedSx, scrollbarSx } from "./styles";

const MUTED = "rgba(255,255,255,0.75)";

/** The rating buttons' size and spacing, and so the picker's width - which
 *  the Remove / Keep pair below matches, so its middle falls on the middle
 *  (neutral) button. */
const RATING_BUTTON_PX = 28;
const RATING_GAP_PX = 3;
const PICKER_WIDTH_PX = RATINGS.length * RATING_BUTTON_PX + (RATINGS.length - 1) * RATING_GAP_PX;

/** Five round buttons from clearly for to clearly against the user, the
 *  chosen one filled with its colour; pressing it again takes the rating
 *  back. The same picker rates each aspect and gives the overall verdict. */
const RatingPicker = ({
  value,
  onChange,
  title,
  overall = false,
}: {
  value: Rating | undefined;
  onChange: (value: Rating | undefined) => void;
  title: string;
  overall?: boolean;
}) => (
  <Box
    role="group"
    aria-label={title}
    sx={{ display: "flex", gap: `${RATING_GAP_PX}px`, flexShrink: 0, ml: "auto" }}
  >
    {RATINGS.map((r) => {
      const chosen = value === r.id;
      const label = overall ? r.overall : r.label;
      return (
        <Tooltip key={r.id} title={label} placement="top">
          <IconButton
            size="small"
            aria-label={label}
            aria-pressed={chosen}
            onClick={() => onChange(chosen ? undefined : r.id)}
            sx={{
              // Border-box and no padding, so a button is exactly this wide
              // and the pair below lines up with the picker.
              boxSizing: "border-box",
              p: 0,
              width: RATING_BUTTON_PX,
              height: RATING_BUTTON_PX,
              border: `1.5px solid ${chosen ? r.color : "rgba(255,255,255,0.25)"}`,
              backgroundColor: chosen ? r.color : "transparent",
              color: chosen ? "white" : r.color,
              "&:hover": { backgroundColor: chosen ? r.color : "rgba(255,255,255,0.10)" },
            }}
          >
            <RatingMark rating={r.id} size={17} />
          </IconButton>
        </Tooltip>
      );
    })}
  </Box>
);

/** What an info icon opens on: the question, then what tips the rating
 *  each way, each led by the thumb it points to. */
const InfoContent = ({ info }: { info: RatingInfo }) => (
  <Box sx={{ fontSize: 12, lineHeight: 1.4, p: 0.25 }}>
    <Box sx={{ fontWeight: 600, mb: 0.75 }}>{info.question}</Box>
    {(
      [
        [ThumbUpIcon, ratingOf("very_good").color, info.up],
        [ThumbDownIcon, ratingOf("very_bad").color, info.down],
      ] as const
    ).map(([Icon, color, text]) => (
      <Box key={text} sx={{ display: "flex", gap: 0.75, alignItems: "flex-start", mt: 0.5 }}>
        <Box
          sx={{
            flexShrink: 0,
            width: 18,
            height: 18,
            borderRadius: "50%",
            backgroundColor: color,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon sx={{ fontSize: 11, color: "white" }} />
        </Box>
        <Box>{text}</Box>
      </Box>
    ))}
  </Box>
);

/** A small info icon that shows what a rating means when pressed, and
 *  hides it on a second press or a press anywhere else. */
const InfoButton = ({ title, info }: { title: string; info: RatingInfo }) => {
  const [open, setOpen] = useState(false);
  return (
    <ClickAwayListener onClickAway={() => setOpen(false)}>
      <span>
        <Tooltip
          open={open}
          title={<InfoContent info={info} />}
          placement="top-start"
          slotProps={{ tooltip: { sx: { maxWidth: 300, backgroundColor: "rgba(30,30,30,0.96)" } } }}
          disableHoverListener
          disableFocusListener
          disableTouchListener
        >
          <IconButton
            size="small"
            aria-label={`About ${title}`}
            aria-expanded={open}
            onClick={() => setOpen((prev) => !prev)}
            sx={{ p: 0.25, color: open ? "white" : "rgba(255,255,255,0.55)" }}
          >
            <InfoOutlinedIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </span>
    </ClickAwayListener>
  );
};

/** One thing to rate: its title, with what it means behind an info icon,
 *  on the left; the picker on the right at a fixed width, so the pickers of
 *  every row stand in one column. */
const RatingRow = ({
  title,
  info,
  value,
  onChange,
  overall,
}: {
  title: string;
  info: RatingInfo;
  value: Rating | undefined;
  onChange: (value: Rating | undefined) => void;
  overall?: boolean;
}) => (
  <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
    <Box sx={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 0.25 }}>
      <Typography sx={{ fontSize: 11.5, color: "white", fontWeight: 600, lineHeight: 1.3 }}>
        {title}
      </Typography>
      <InfoButton title={title} info={info} />
    </Box>
    <RatingPicker title={title} value={value} onChange={onChange} overall={overall} />
  </Box>
);

type AssessmentProps = {
  crux: CruxEntry;
  onAnswer: (factor: Factor, value: Rating | undefined) => void;
  onOverall: (value: Rating | undefined) => void;
  onKeep: (keep: boolean | undefined) => void;
};

/** Under an opened Crux: the user rates each aspect from clearly for to
 *  clearly against them, then - on the same scale, right below, where the
 *  pattern of their answers is in view - gives their own overall verdict,
 *  and decides whether the Crux stays in the list. Nothing is worked out
 *  for them. */
const Assessment = ({ crux, onAnswer, onOverall, onKeep }: AssessmentProps) => (
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

    <Typography sx={{ fontSize: 11.5, color: MUTED, mb: 1 }}>
      Rate how each aspect weighs: from clearly in your favour (big thumb up) to clearly
      against you (big thumb down).
    </Typography>

    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {questionsFor(crux).map((q) => (
        <RatingRow
          key={q.factor}
          title={q.title}
          info={q}
          value={crux.answers[q.factor]}
          onChange={(v) => onAnswer(q.factor, v)}
        />
      ))}
    </Box>

    {/* A Runout area's one rating is its overall rating already. */}
    {hasOwnOverall(crux) && (
      <Box sx={{ borderTop: "1px solid rgba(255,255,255,0.18)", mt: 1, pt: 1 }}>
        <RatingRow
          overall
          title="Overall assessment"
          info={OVERALL_INFO}
          value={crux.overall}
          onChange={onOverall}
        />
      </Box>
    )}

    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1.25 }}>
      <Typography sx={{ flex: 1, fontSize: 12, color: "white", fontWeight: 600 }}>
        Keep the crux?
      </Typography>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={crux.keep === undefined ? null : crux.keep ? "keep" : "remove"}
        onChange={(_, next: "keep" | "remove" | null) =>
          onKeep(next === null ? undefined : next === "keep")
        }
        sx={{
          width: PICKER_WIDTH_PX,
          flexShrink: 0,
          "& .MuiToggleButton-root": {
            flex: 1,
            px: 0,
            py: 0.25,
            fontSize: 11.5,
            textTransform: "none",
            color: MUTED,
            borderColor: "rgba(255,255,255,0.25)",
          },
          "& .MuiToggleButton-root.Mui-selected": {
            color: "white",
            backgroundColor: COLORS.teal,
            "&:hover": { backgroundColor: COLORS.teal },
          },
        }}
      >
        <ToggleButton value="remove">Remove</ToggleButton>
        <ToggleButton value="keep">Keep</ToggleButton>
      </ToggleButtonGroup>
    </Box>
  </Box>
);

type CruxRowProps = {
  crux: CruxEntry;
  open: boolean;
  /** Being edited, moved or having its extent edited: shown in the open
   *  colour, without its assessment folded out. */
  highlighted: boolean;
  onClick: () => void;
  onEdit: () => void;
  onMove: () => void;
  onEditExtent: () => void;
  onDelete: () => void;
};

/** One Crux in the list, with the user's verdict at its end once they
 *  have kept it - the same disc its marker carries. The three dots open what
 *  can be done to it: edit it, move its marker, edit the stretch it
 *  colours, or delete it. */
const CruxRow = ({
  crux,
  open,
  highlighted,
  onClick,
  onEdit,
  onMove,
  onEditExtent,
  onDelete,
}: CruxRowProps) => {
  const verdict = verdictOf(crux);
  const icons = dangerIcons(crux);
  const badge = cruxBadge(crux);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const closeMenu = () => setMenuAnchor(null);
  // Marked from the moment its menu opens, so it is clear which Crux the
  // menu - and whatever is chosen in it - is about.
  const marked = open || highlighted || menuAnchor !== null;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        borderRadius: open ? "8px 8px 0 0" : 1.5,
        background: marked ? "rgba(54,126,152,0.35)" : "rgba(255,255,255,0.06)",
        "&:hover": { background: marked ? "rgba(54,126,152,0.45)" : "rgba(255,255,255,0.12)" },
      }}
    >
      <ButtonBase
        onClick={onClick}
        aria-expanded={open}
        sx={{
          flex: 1,
          minWidth: 0,
          justifyContent: "flex-start",
          gap: 1,
          pl: 1,
          py: 0.5,
          borderRadius: "inherit",
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
            <Box component="span" sx={{ ml: 0.75, color: lighten(dangerColor(crux), 0.25) }}>
              {badge}
            </Box>
          )}
          {crux.source === "manual" && (
            <Box component="span" sx={{ ml: 0.75, color: "rgba(255,255,255,0.55)", fontSize: 11 }}>
              manually added
            </Box>
          )}
        </Typography>
        {verdict && (
          <Box
            component="span"
            title={verdict === "kept" ? "Kept - not rated" : `Kept - ${ratingOf(verdict).overall}`}
            sx={{ display: "flex" }}
          >
            <VerdictDisc verdict={verdict} size={18} />
          </Box>
        )}
      </ButtonBase>
      <IconButton
        size="small"
        aria-label={`Options for crux ${crux.number}`}
        aria-haspopup="menu"
        onClick={(e) => setMenuAnchor(e.currentTarget)}
        sx={{ color: "rgba(255,255,255,0.75)", mr: 0.25 }}
      >
        <MoreVertIcon fontSize="small" />
      </IconButton>
      <Menu anchorEl={menuAnchor} open={menuAnchor !== null} onClose={closeMenu}>
        <MenuItem
          onClick={() => {
            closeMenu();
            onEdit();
          }}
        >
          <ListItemIcon>
            <EditOutlinedIcon fontSize="small" />
          </ListItemIcon>
          Edit crux
        </MenuItem>
        <MenuItem
          onClick={() => {
            closeMenu();
            onMove();
          }}
        >
          <ListItemIcon>
            <OpenWithIcon fontSize="small" />
          </ListItemIcon>
          Move marker
        </MenuItem>
        <MenuItem
          onClick={() => {
            closeMenu();
            onEditExtent();
          }}
        >
          <ListItemIcon>
            <StraightenIcon fontSize="small" />
          </ListItemIcon>
          Edit extent
        </MenuItem>
        <MenuItem
          onClick={() => {
            closeMenu();
            onDelete();
          }}
        >
          <ListItemIcon>
            <DeleteOutlineIcon fontSize="small" />
          </ListItemIcon>
          Delete
        </MenuItem>
      </Menu>
    </Box>
  );
};

type ShelfProps = {
  title: string;
  cruxes: readonly CruxEntry[];
  struck?: boolean;
  onRestore: (cruxId: string) => void;
};

/** A greyed-out shelf under the list: Cruxes that are not in play, each
 *  with a way to bring it back. */
const Shelf = ({ title, cruxes, struck = false, onRestore }: ShelfProps) => (
  <Box component="li" sx={{ mt: 1 }}>
    <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.6)", mb: 0.5 }}>
      {title} ({cruxes.length})
    </Typography>
    {cruxes.map((crux) => (
      <Box
        key={crux.id}
        sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.25, opacity: 0.6 }}
      >
        <Typography
          sx={{
            flex: 1,
            fontSize: 12,
            color: "white",
            textDecoration: struck ? "line-through" : "none",
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
);

type CruxListProps = {
  cruxes: readonly CruxEntry[];
  /** The route has been through the identifier, so an empty list means it
   *  found nothing rather than that it has not been asked. */
  analysed: boolean;
  activeId: string | null;
  /** The Crux being edited, moved or having its extent edited, if any. */
  highlightedId: string | null;
  onActivate: (crux: CruxEntry) => void;
  onAnswer: (cruxId: string, factor: Factor, value: Rating | undefined) => void;
  onOverall: (cruxId: string, value: Rating | undefined) => void;
  onKeep: (cruxId: string, keep: boolean | undefined) => void;
  onRestore: (cruxId: string) => void;
  onDelete: (cruxId: string) => void;
  onUndelete: (cruxId: string) => void;
  /** Start moving a Crux: the next map click puts it on the route there. */
  /** Open a Crux's name, symbol and colour for editing. */
  onEdit: (crux: CruxEntry) => void;
  onMove: (crux: CruxEntry) => void;
  /** Start editing the stretch a Crux colours, with handles on the map. */
  onEditExtent: (crux: CruxEntry) => void;
  open: boolean;
  onToggle: () => void;
  /** A Crux is being placed, moved or its extent edited, so the button
   *  gives up instead. */
  placing: boolean;
  /** What the map is waiting for, in words, while `placing`. */
  placingText: string;
  onPlace: () => void;
  /** An extent is being edited: it is kept with Done, or put back to what
   *  it had with Reset. */
  editingExtent: boolean;
  onFinishExtent: () => void;
  onResetExtent: () => void;
};

/** The Selected route's Cruxes in route order, numbered like their markers:
 *  those kept, or not decided yet. Below them, greyed out, wait the ones the
 *  user chose not to keep and then the deleted ones, each to be restored.
 *  Clicking a Crux takes the map there and opens its assessment. Can be
 *  folded away to its heading; the markers on the map stay either way. */
const CruxList = ({
  cruxes,
  analysed,
  activeId,
  highlightedId,
  onActivate,
  onAnswer,
  onOverall,
  onKeep,
  onRestore,
  onDelete,
  onUndelete,
  onEdit,
  onMove,
  onEditExtent,
  open,
  onToggle,
  placing,
  placingText,
  onPlace,
  editingExtent,
  onFinishExtent,
  onResetExtent,
}: CruxListProps) => {
  const active = cruxes.filter((c) => shelfOf(c) === "active");
  const notKept = cruxes.filter((c) => shelfOf(c) === "not_kept");
  const deleted = cruxes.filter((c) => shelfOf(c) === "deleted");

  // Opened from the map, the Crux may be scrolled out of sight in here.
  const activeRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  return (
    <Box sx={{ flex: open ? 1 : "none", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: open ? 0.75 : 0 }}>
        <Typography sx={{ color: "white", fontSize: 14, fontWeight: 600 }}>
          Cruxes ({active.length})
        </Typography>
        {active.length > 0 && (
          <Typography sx={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>
            · {active.filter(isDecided).length} assessed
          </Typography>
        )}
        <CollapseToggle open={open} onToggle={onToggle} what="the list of cruxes" />

        <Box sx={{ flex: 1 }} />

        {/* Pressed again while placing or moving, it gives up. */}
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
          {placingText}
        </Typography>
      )}

      {editingExtent && (
        <Box sx={{ display: "flex", gap: 1, mb: 0.75 }}>
          <Button
            variant="outlined"
            size="small"
            onClick={onResetExtent}
            sx={{ ...outlinedSx, flex: 1, fontSize: 12, py: 0.1 }}
          >
            Reset
          </Button>
          <Button
            variant="outlined"
            size="small"
            onClick={onFinishExtent}
            sx={{
              ...outlinedSx,
              flex: 2,
              fontSize: 12,
              py: 0.1,
              backgroundColor: "rgba(54,126,152,0.35)",
            }}
          >
            Done
          </Button>
        </Box>
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
          {active.map((crux) => {
            const isActive = crux.id === activeId;
            return (
              <Box component="li" key={crux.id} ref={isActive ? activeRef : undefined}>
                <CruxRow
                  crux={crux}
                  open={isActive}
                  highlighted={crux.id === highlightedId}
                  onClick={() => onActivate(crux)}
                  onEdit={() => onEdit(crux)}
                  onMove={() => onMove(crux)}
                  onEditExtent={() => onEditExtent(crux)}
                  onDelete={() => onDelete(crux.id)}
                />
                {isActive && (
                  <Assessment
                    crux={crux}
                    onAnswer={(factor, value) => onAnswer(crux.id, factor, value)}
                    onOverall={(value) => onOverall(crux.id, value)}
                    onKeep={(keep) => {
                      onKeep(crux.id, keep);
                      // Kept: evaluated, so it folds away. Removed: it
                      // leaves the list anyway.
                      if (keep === true) onActivate(crux);
                    }}
                  />
                )}
              </Box>
            );
          })}

          {notKept.length > 0 && (
            <Shelf title="Removed" cruxes={notKept} onRestore={onRestore} />
          )}
          {deleted.length > 0 && (
            <Shelf title="Deleted" cruxes={deleted} struck onRestore={onUndelete} />
          )}
        </Box>
      )}
    </Box>
  );
};

export default CruxList;
