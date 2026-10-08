import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Dialog from "@mui/material/Dialog";
import Slider from "@mui/material/Slider";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import CheckIcon from "@mui/icons-material/Check";

import { problemHazards } from "../crux/assessment";
import { PROBLEM_ICONS } from "../dangerClasses";
import type { CruxProblem, ManualCruxInput } from "../types";
import { COLORS, CRUX_COLORS, dangerColor } from "../theme";
import { accentOutlinedSx, outlinedSx } from "./styles";

/** The colours a Crux is drawn in anyway, so one placed by hand sits among
 *  the identified ones without inventing a new meaning. */
const COLOR_CHOICES = [
  { color: CRUX_COLORS.danger, name: "Red" },
  { color: CRUX_COLORS.steep, name: "Dark orange" },
  { color: CRUX_COLORS.runout, name: "Light orange" },
  { color: CRUX_COLORS.snow, name: "Blue" },
];

/** The symbols a Crux can be drawn with: the problems the identifier names,
 *  each with the icon its marker carries. Shown as icons alone; the name is
 *  in the tooltip. */
const SYMBOL_CHOICES: { problem: CruxProblem; name: string }[] = [
  { problem: "steep_slope", name: "Steep slope" },
  { problem: "release_area", name: "Probable release area" },
  { problem: "fall_hazard", name: "Fall hazard" },
  { problem: "runout_area", name: "Runout area" },
  { problem: "snow_check", name: "Snow conditions check" },
];

/** The colour a problem is drawn in when the user has not chosen one. */
export const problemColor = (problem: CruxProblem): string => dangerColor(problemHazards(problem));

const Label = ({ children }: { children: string }) => (
  <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, mt: 2, mb: 0.75 }}>
    {children}
  </Typography>
);

/** What a Crux is called, what it is, and its colour - the part of a Crux
 *  the user describes, the same whether adding one or editing it. */
export type CruxDetails = { description: string; problem: CruxProblem; color: string };

/** The details as they are being filled in. The colour follows the symbol
 *  until the user picks one themselves. */
const useDetails = (initial: CruxDetails, colorChosen: boolean) => {
  const [details, setDetails] = useState(initial);
  const [touched, setTouched] = useState(colorChosen);
  return {
    details,
    setDescription: (description: string) => setDetails((d) => ({ ...d, description })),
    setProblem: (problem: CruxProblem) =>
      setDetails((d) => ({ ...d, problem, color: touched ? d.color : problemColor(problem) })),
    setColor: (color: string) => {
      setTouched(true);
      setDetails((d) => ({ ...d, color }));
    },
  };
};

const DetailsFields = ({
  details,
  setDescription,
  setProblem,
  setColor,
  onSubmit,
}: ReturnType<typeof useDetails> & { onSubmit: () => void }) => (
  <>
    <Label>What is the crux?</Label>
    <TextField
      autoFocus
      fullWidth
      multiline
      minRows={2}
      maxRows={5}
      size="small"
      placeholder="E.g. wind-loaded lip under the ridge"
      value={details.description}
      onChange={(e) => setDescription(e.target.value)}
      onKeyDown={(e) => {
        // Enter submits; Shift+Enter is a new line.
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          onSubmit();
        }
      }}
      sx={{
        "& .MuiInputBase-root": { color: "white", fontSize: 13 },
        "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.3)" },
        "& .MuiInputBase-root.Mui-focused .MuiOutlinedInput-notchedOutline": {
          borderColor: COLORS.teal,
        },
      }}
    />

    <Label>Symbol</Label>
    <Box sx={{ display: "flex", gap: 0.75 }}>
      {SYMBOL_CHOICES.map(({ problem, name }) => {
        const chosen = details.problem === problem;
        const Icon = PROBLEM_ICONS[problem];
        return (
          <Tooltip key={problem} title={name}>
            <ButtonBase
              aria-label={name}
              aria-pressed={chosen}
              onClick={() => setProblem(problem)}
              sx={{
                width: 44,
                height: 40,
                borderRadius: 1.5,
                color: "white",
                border: `1.5px solid ${chosen ? COLORS.teal : "rgba(255,255,255,0.2)"}`,
                backgroundColor: chosen ? "rgba(54,126,152,0.35)" : "transparent",
                "&:hover": { backgroundColor: chosen ? "rgba(54,126,152,0.45)" : "rgba(255,255,255,0.08)" },
              }}
            >
              <Icon sx={{ fontSize: 22 }} />
            </ButtonBase>
          </Tooltip>
        );
      })}
    </Box>

    <Label>Colour</Label>
    <Box sx={{ display: "flex", gap: 1.25 }}>
      {COLOR_CHOICES.map((c) => (
        <ButtonBase
          key={c.color}
          aria-label={c.name}
          aria-pressed={details.color === c.color}
          title={c.name}
          onClick={() => setColor(c.color)}
          sx={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            backgroundColor: c.color,
            border: "2px solid white",
            outline: details.color === c.color ? `2px solid ${COLORS.teal}` : "none",
            outlineOffset: 2,
          }}
        >
          {details.color === c.color && <CheckIcon sx={{ color: "white", fontSize: 18 }} />}
        </ButtonBase>
      ))}
    </Box>
  </>
);

const Actions = ({
  submitLabel,
  onCancel,
  onSubmit,
}: {
  submitLabel: string;
  onCancel: () => void;
  onSubmit: () => void;
}) => (
  <Box sx={{ display: "flex", gap: 1, mt: 2.5 }}>
    <Button
      variant="outlined"
      size="small"
      onClick={onCancel}
      sx={{ ...outlinedSx, flex: 1, fontSize: 13 }}
    >
      Cancel
    </Button>
    <Button variant="outlined" size="small" onClick={onSubmit} sx={{ ...accentOutlinedSx, flex: 2 }}>
      {submitLabel}
    </Button>
  </Box>
);

const CruxDialog = ({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) => (
  <Dialog
    open={open}
    onClose={onClose}
    slotProps={{
      paper: {
        sx: {
          width: 360,
          maxWidth: "calc(100vw - 32px)",
          m: 2,
          backgroundColor: COLORS.panel,
          backgroundImage: "none",
          border: "1px solid rgba(255,255,255,0.15)",
        },
      },
    }}
  >
    {/* Mounted afresh each time, so it starts from what it is given. */}
    {open && children}
  </Dialog>
);

const Title = ({ children }: { children: string }) => (
  <Typography sx={{ color: "white", fontSize: 18, fontWeight: 600 }}>{children}</Typography>
);

export type AddCruxDefaults = {
  problem: CruxProblem;
};

/** The longest stretch of line a hand-placed Crux can be asked to colour. */
const MAX_STRETCH_M = 1000;
const STRETCH_STEP_M = 10;

/** What the stretch looks like so far, for the map to preview while the
 *  form is open; null once it is closed. */
export type StretchPreview = { color: string; length_m: number };

type AddCruxFormProps = {
  /** What the analysed line says at the spot: the symbol the Crux starts
   *  with, which also decides its questions - one for a Runout area, all
   *  five otherwise. */
  defaults: AddCruxDefaults;
  /** How much route is left ahead of the spot, which caps the stretch. */
  maxLength: number;
  onPreview: (preview: StretchPreview | null) => void;
  onCancel: () => void;
  onAdd: (input: Omit<ManualCruxInput, "position" | "distance_m">) => void;
};

/** A hand-placed Crux: what the user says it is, its symbol and colour, and
 *  how much of the line ahead it colours. It starts from what the analysed
 *  line says where it was placed. */
const AddCruxForm = ({ defaults, maxLength, onPreview, onCancel, onAdd }: AddCruxFormProps) => {
  const fields = useDetails(
    { description: "", problem: defaults.problem, color: problemColor(defaults.problem) },
    false
  );
  const { color } = fields.details;
  const [length, setLength] = useState(0);
  const longest = Math.min(MAX_STRETCH_M, Math.floor(maxLength / STRETCH_STEP_M) * STRETCH_STEP_M);

  useEffect(() => {
    onPreview({ color, length_m: length });
    return () => onPreview(null);
  }, [color, length, onPreview]);

  const add = () => onAdd({ ...fields.details, length_m: length });

  return (
    <Box sx={{ p: 2.5 }}>
      <Title>Add crux</Title>
      <DetailsFields {...fields} onSubmit={add} />

      {longest > 0 && (
        <>
          <Label>Colour the line ahead</Label>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 0.5 }}>
            <Slider
              value={length}
              min={0}
              max={longest}
              step={STRETCH_STEP_M}
              size="small"
              aria-label="Length of line to colour"
              onChange={(_, v) => setLength(v as number)}
              sx={{ color, "& .MuiSlider-thumb": { width: 14, height: 14 } }}
            />
            <Typography
              sx={{
                fontSize: 12,
                color: "white",
                minWidth: 52,
                textAlign: "right",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {length === 0 ? "None" : `${length} m`}
            </Typography>
          </Box>
          <Typography sx={{ fontSize: 11.5, color: "rgba(255,255,255,0.65)" }}>
            Starts at the marker and runs along the route in your direction of travel.
          </Typography>
        </>
      )}

      <Actions submitLabel="Add crux" onCancel={onCancel} onSubmit={add} />
    </Box>
  );
};

type AddCruxDialogProps = AddCruxFormProps & {
  /** Whether a spot has been picked and is waiting to be added. */
  open: boolean;
};

const AddCruxDialog = ({ open, ...form }: AddCruxDialogProps) => (
  <CruxDialog open={open} onClose={form.onCancel}>
    <AddCruxForm {...form} />
  </CruxDialog>
);

type EditCruxFormProps = {
  /** What the Crux is now, to start from. */
  initial: CruxDetails;
  /** Whether its colour is one the user chose, rather than its symbol's -
   *  if not, it keeps following the symbol. */
  colorChosen: boolean;
  onCancel: () => void;
  onSave: (details: CruxDetails) => void;
};

/** Changing what a Crux is called, its symbol and its colour - for any
 *  Crux, identified or placed by hand. Where it is and what it colours are
 *  edited from its menu instead. */
const EditCruxForm = ({ initial, colorChosen, onCancel, onSave }: EditCruxFormProps) => {
  const fields = useDetails(initial, colorChosen);
  const save = () => onSave(fields.details);
  return (
    <Box sx={{ p: 2.5 }}>
      <Title>Edit crux</Title>
      <DetailsFields {...fields} onSubmit={save} />
      <Actions submitLabel="Save" onCancel={onCancel} onSubmit={save} />
    </Box>
  );
};

type EditCruxDialogProps = Omit<EditCruxFormProps, "initial"> & {
  /** What the Crux is now; null while no Crux is being edited. */
  initial: CruxDetails | null;
};

export const EditCruxDialog = ({ initial, ...form }: EditCruxDialogProps) => (
  <CruxDialog open={initial !== null} onClose={form.onCancel}>
    {initial && <EditCruxForm initial={initial} {...form} />}
  </CruxDialog>
);

export default AddCruxDialog;
