import havard from "./assets/users/havard.jpg";
import markus from "./assets/users/markus.jpg";
import andreas from "./assets/users/andreas.jpg";
import finn from "./assets/users/finn.jpg";
import halvor from "./assets/users/halvor.jpg";
import type { Expert } from "./types";

/** Profile pictures by expert id (the validation app's ids). */
const PHOTOS: Record<string, string> = { havard, markus, andreas, finn, halvor };

export function Avatar({ user, size }: { user: Expert; size: number }) {
  const photo = PHOTOS[user.id];
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {photo ? <img src={photo} alt="" /> : user.name[0]}
    </span>
  );
}
