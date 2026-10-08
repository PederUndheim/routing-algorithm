import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import ThumbDownIcon from "@mui/icons-material/ThumbDown";
import ThumbUpIcon from "@mui/icons-material/ThumbUp";

import { ratingOf } from "../crux/assessment";
import type { Verdict } from "../crux/assessment";
import type { Rating } from "../types";

/** A rating's mark: a big or small thumb up or down, or a dash between. Its
 *  colour is the caller's - filled buttons want white, text wants the
 *  rating's own. */
const RatingMark = ({ rating, size }: { rating: Rating; size: number }) => {
  const { thumb, strong } = ratingOf(rating);
  const Icon = thumb === "up" ? ThumbUpIcon : thumb === "down" ? ThumbDownIcon : HorizontalRuleIcon;
  return <Icon sx={{ fontSize: thumb && !strong ? Math.round(size * 0.7) : size }} />;
};

/** The verdict as a white disc, the rating's thumb inside
 *  in its own colour - white, so it reads on any colour of pill and on the
 *  dark drawer alike. Plain styles, so it renders into a static marker too. */
export const VerdictDisc = ({
  verdict,
  size,
  shadow = false,
}: {
  verdict: Exclude<Verdict, null>;
  size: number;
  /** Lifted off the map with a shadow, as the marker beside it is. */
  shadow?: boolean;
}) => {
  const rating = verdict === "kept" ? null : ratingOf(verdict);
  // Kept without a rating: the disc stays empty - a verdict still to give.
  const Icon = !rating
    ? null
    : rating.thumb === "up"
      ? ThumbUpIcon
      : rating.thumb === "down"
        ? ThumbDownIcon
        : HorizontalRuleIcon;
  const small = rating?.thumb && !rating.strong;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: size,
        height: size,
        borderRadius: "50%",
        background: "white",
        flexShrink: 0,
        boxShadow: shadow ? "0 1px 4px rgba(0,0,0,0.45)" : undefined,
      }}
    >
      {Icon && rating && (
        <Icon style={{ fontSize: Math.round(size * (small ? 0.58 : 0.8)), color: rating.color }} />
      )}
    </span>
  );
};

export default RatingMark;
