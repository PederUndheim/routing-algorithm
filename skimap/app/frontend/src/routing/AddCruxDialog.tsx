import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Dialog from "@mui/material/Dialog";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CheckIcon from "@mui/icons-material/Check";

import { problemHazards } from "../crux/assessment";
import type { CruxProblem, ManualCruxInput, SlopeCategory } from "../types";
import { COLORS, CRUX_COLORS, dangerColor } from "../theme";
import { accentOutlinedSx, outlinedSx } from "./styles";

/** The colours a Crux is drawn in anyway, so one placed by hand sits among
 *  the identified ones without inventing a new meaning. */
const COLOR_CHOICES = [
  { color: CRUX_COLORS.danger, name: "Red" },
  { color: CRUX_COLORS.steep, name: "Dark orange" },
  { color: CRUX_COLORS.runout, name: "Light orange" },
];

/** Where the analysed line says nothing - not analysed, or no terrain data
 *  - a hand-placed Crux is taken as moderately steep, so it still gets all
 *  five questions. */
const FALLBACK_CATEGORY: SlopeCategory = "30_34";

const Label = ({ children }: { children: string }) => (
  <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, mt: 2, mb: 0.75 }}>
    {children}
  </Typography>
);

export type AddCruxDefaults = {
  category: SlopeCategory | null;
  problem: CruxProblem;
};

type AddCruxFormProps = {
  /** What the analysed line says at the spot: the Crux's slope category -
   *  which decides its questions - and the symbol it is drawn with. */
  defaults: AddCruxDefaults;
  onCancel: () => void;
  onAdd: (input: Omit<ManualCruxInput, "position" | "distance_m">) => void;
};

/** A hand-placed Crux: what the user says it is, and its colour. Everything
 *  else comes from the analysed line where it was placed. */
const AddCruxForm = ({ defaults, onCancel, onAdd }: AddCruxFormProps) => {
  const [color, setColor] = useState<string>(() => dangerColor(problemHazards(defaults.problem)));
  const [description, setDescription] = useState("");

  const add = () =>
    onAdd({
      category: defaults.category ?? FALLBACK_CATEGORY,
      problem: defaults.problem,
      color,
      description,
    });

  return (
    <Box sx={{ p: 2.5 }}>
      <Typography sx={{ color: "white", fontSize: 18, fontWeight: 600 }}>Add crux</Typography>

      <Label>What is the crux?</Label>
      <TextField
        autoFocus
        fullWidth
        multiline
        minRows={2}
        maxRows={5}
        size="small"
        placeholder="E.g. wind-loaded lip under the ridge"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={(e) => {
          // Enter adds it; Shift+Enter is a new line.
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            add();
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

      <Label>Colour</Label>
      <Box sx={{ display: "flex", gap: 1.25 }}>
        {COLOR_CHOICES.map((c) => (
          <ButtonBase
            key={c.color}
            aria-label={c.name}
            aria-pressed={color === c.color}
            title={c.name}
            onClick={() => setColor(c.color)}
            sx={{
              width: 30,
              height: 30,
              borderRadius: "50%",
              backgroundColor: c.color,
              border: "2px solid white",
              outline: color === c.color ? `2px solid ${COLORS.teal}` : "none",
              outlineOffset: 2,
            }}
          >
            {color === c.color && <CheckIcon sx={{ color: "white", fontSize: 18 }} />}
          </ButtonBase>
        ))}
      </Box>

      <Box sx={{ display: "flex", gap: 1, mt: 2.5 }}>
        <Button
          variant="outlined"
          size="small"
          onClick={onCancel}
          sx={{ ...outlinedSx, flex: 1, fontSize: 13 }}
        >
          Cancel
        </Button>
        <Button
          variant="outlined"
          size="small"
          onClick={add}
          sx={{ ...accentOutlinedSx, flex: 2 }}
        >
          Add crux
        </Button>
      </Box>
    </Box>
  );
};

type AddCruxDialogProps = AddCruxFormProps & {
  /** Whether a spot has been picked and is waiting to be added. */
  open: boolean;
};

const AddCruxDialog = ({ open, ...form }: AddCruxDialogProps) => (
  <Dialog
    open={open}
    onClose={form.onCancel}
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
    {/* Mounted afresh each time, so it starts from this spot's defaults. */}
    {open && <AddCruxForm {...form} />}
  </Dialog>
);

export default AddCruxDialog;
