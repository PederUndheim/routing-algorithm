import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import Typography from "@mui/material/Typography";

import { COLORS } from "../theme";
import { accentOutlinedSx, outlinedSx } from "./styles";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  /** What will happen, in words. */
  children: ReactNode;
};

/** Asks before something that throws the user's work away. Cancel is the
 *  safe way out, and the default. */
const ConfirmDialog = ({
  open,
  title,
  confirmLabel,
  onCancel,
  onConfirm,
  children,
}: ConfirmDialogProps) => (
  <Dialog
    open={open}
    onClose={onCancel}
    slotProps={{
      paper: {
        sx: {
          width: 380,
          maxWidth: "calc(100vw - 32px)",
          m: 2,
          backgroundColor: COLORS.panel,
          backgroundImage: "none",
          border: "1px solid rgba(255,255,255,0.15)",
        },
      },
    }}
  >
    <Box sx={{ p: 2.5 }}>
      <Typography sx={{ color: "white", fontSize: 18, fontWeight: 600, mb: 1.25 }}>
        {title}
      </Typography>
      <Typography sx={{ color: "rgba(255,255,255,0.85)", fontSize: 13 }}>{children}</Typography>
      <Box sx={{ display: "flex", gap: 1, mt: 2.5 }}>
        <Button
          autoFocus
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
          onClick={onConfirm}
          sx={{ ...accentOutlinedSx, flex: 1 }}
        >
          {confirmLabel}
        </Button>
      </Box>
    </Box>
  </Dialog>
);

export default ConfirmDialog;
