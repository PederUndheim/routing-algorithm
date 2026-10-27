import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchUsers, sendOp } from "./api";
import { Avatar } from "./Avatar";
import { loadIndex } from "./data";
import { Reviewer } from "./Reviewer";
import { SaveQueue, type SaveStatus } from "./saveQueue";
import type { CorridorInfo, User } from "./types";

const CODE_KEY = "validering.code";
const USER_KEY = "validering.user";

const read = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const write = (key: string, value: string | null) => {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // remembered for this tab only
  }
};

export function App() {
  const [code, setCode] = useState<string | null>(() => read(CODE_KEY));
  const [users, setUsers] = useState<User[] | null>(null);
  const [userId, setUserId] = useState<string | null>(() => read(USER_KEY));
  const [index, setIndex] = useState<CorridorInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<SaveStatus>({ kind: "saved" });
  const [attempt, setAttempt] = useState(0);

  // One queue for the life of the page, whoever is logged in: an op carries
  // its own user, so switching users never strands the last one's changes.
  const codeRef = useRef(code);
  codeRef.current = code;
  const queue = useMemo(() => new SaveQueue((op) => sendOp(codeRef.current ?? "", op)), []);

  useEffect(() => {
    const unsubscribe = queue.subscribe(setStatus);
    const online = () => queue.flush();
    const leaving = (e: BeforeUnloadEvent) => {
      if (queue.pending.length) e.preventDefault();
    };
    window.addEventListener("online", online);
    window.addEventListener("beforeunload", leaving);
    queue.flush();
    return () => {
      unsubscribe();
      window.removeEventListener("online", online);
      window.removeEventListener("beforeunload", leaving);
    };
  }, [queue]);

  useEffect(() => {
    loadIndex().then(setIndex, (e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!code) return;
    setError(null);
    fetchUsers(code).then(
      (list) => {
        setUsers(list);
        queue.flush(); // anything held back by a wrong code
      },
      (e: Error) => {
        if (e instanceof ApiError && e.status === 401) {
          write(CODE_KEY, null);
          setCode(null);
          setError("Feil tilgangskode");
        } else {
          setError(`Får ikke kontakt med serveren (${e.message})`);
        }
      });
  }, [code, attempt, queue]);

  const pickUser = (id: string | null) => {
    write(USER_KEY, id);
    setUserId(id);
  };

  if (!code || (!users && error)) {
    return <Login error={error} onCode={(c) => { write(CODE_KEY, c); setCode(c); }}
                  retry={code ? () => setAttempt((n) => n + 1) : undefined} />;
  }
  if (!users || !index) {
    return <div className="center-screen">{error ?? "Laster …"}</div>;
  }
  const user = users.find((u) => u.id === userId);
  if (!user) {
    return (
      <div className="center-screen">
        <h1>Hvem er du?</h1>
        <div className="user-grid">
          {users.map((u) => (
            <button key={u.id} className={`user-btn ${u.id === "test" ? "test" : ""}`} onClick={() => pickUser(u.id)}>
              {u.id !== "test" && <Avatar user={u} size={56} />}
              {u.name}
            </button>
          ))}
        </div>
        <button className="link" onClick={() => { write(CODE_KEY, null); setCode(null); setUsers(null); }}>
          Logg ut
        </button>
      </div>
    );
  }
  return <Reviewer key={user.id} code={code} user={user} index={index} queue={queue} status={status}
                   onSwitchUser={() => pickUser(null)} />;
}

function Login({ error, onCode, retry }: { error: string | null; onCode: (c: string) => void; retry?: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="center-screen">
      <h1>Korridorvalidering</h1>
      <form className="login" onSubmit={(e) => { e.preventDefault(); if (value.trim()) onCode(value.trim()); }}>
        <input autoFocus type="password" placeholder="Tilgangskode" value={value}
               onChange={(e) => setValue(e.target.value)} />
        <button className="primary-btn" type="submit">Logg inn</button>
      </form>
      {error && <p className="error">{error}</p>}
      {retry && <button className="link" onClick={retry}>Prøv igjen</button>}
    </div>
  );
}
