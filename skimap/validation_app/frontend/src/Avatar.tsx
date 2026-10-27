import havard from "./assets/users/havard.jpg";
import markus from "./assets/users/markus.jpg";
import andreas from "./assets/users/andreas.jpg";
import finn from "./assets/users/finn.jpg";
import type { User } from "./types";

/** Profile pictures by user id (backend/verdicts.py). A user without one -
 *  the test user - gets their initial. */
const PHOTOS: Record<string, string> = { havard, markus, andreas, finn };

export function Avatar({ user, size }: { user: User; size: number }) {
  const photo = PHOTOS[user.id];
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {photo ? <img src={photo} alt="" /> : user.name[0]}
    </span>
  );
}
