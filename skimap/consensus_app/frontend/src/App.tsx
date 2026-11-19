import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchMeetings, sendOp } from "./api";
import { Avatar } from "./Avatar";
import { loadIndex } from "./data";
import { MeetingView } from "./MeetingView";
import { SaveQueue, type SaveStatus } from "./saveQueue";
import type { CorridorInfo, Meeting } from "./types";

const CODE_KEY = "konsensus.code";
/** The meeting open, as its id - or "review:<id>" for its review of the
 *  auto-classification. */
const MEETING_KEY = "konsensus.meeting";
const REVIEW = "review:";

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
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [meetingId, setMeetingId] = useState<string | null>(() => read(MEETING_KEY));
  const [index, setIndex] = useState<CorridorInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<SaveStatus>({ kind: "saved" });
  const [attempt, setAttempt] = useState(0);

  // One queue for the life of the page: an op carries its own meeting, so
  // switching meetings never strands the last one's changes.
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
    fetchMeetings(code).then(
      (list) => {
        setMeetings(list);
        queue.flush();
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

  const pickMeeting = (id: string | null) => {
    write(MEETING_KEY, id);
    setMeetingId(id);
  };

  if (!code || (!meetings && error)) {
    return <Login error={error} onCode={(c) => { write(CODE_KEY, c); setCode(c); }}
                  retry={code ? () => setAttempt((n) => n + 1) : undefined} />;
  }
  if (!meetings || !index) {
    return <div className="center-screen">{error ?? "Laster …"}</div>;
  }
  const review = !!meetingId?.startsWith(REVIEW);
  const meeting = meetings.find((m) => m.id === (review ? meetingId?.slice(REVIEW.length) : meetingId));
  if (!meeting) {
    return (
      <div className="center-screen">
        <h1>Konsensusmøte</h1>
        <p className="lead">Velg møte</p>
        <div className="meeting-grid">
          {meetings.map((m) => (
            <button key={m.id} className={`meeting-btn ${m.test ? "test" : ""}`} onClick={() => pickMeeting(m.id)}>
              <span className="meeting-date">{m.label}</span>
              {!m.test && (
                <span className="meeting-people">
                  {m.experts.map((e) => (
                    <span key={e.id} className="meeting-person"><Avatar user={e} size={40} />{e.name}</span>
                  ))}
                </span>
              )}
              <span className="meeting-count">{m.corridors.length} korridorer</span>
            </button>
          ))}
        </div>
        <h2 className="start-section">Gjennomgang av auto-klassifisering</h2>
        <p className="lead small">De auto-klassifiserte korridorene, mest tvilsomme først – ta dem tilbake til diskusjon ved behov.</p>
        <div className="meeting-grid">
          {meetings.map((m) => (
            <button key={m.id} className={`review-btn ${m.test ? "test" : ""}`} onClick={() => pickMeeting(REVIEW + m.id)}>
              <span className="meeting-date">{m.label}</span>
              {!m.test && <span className="meeting-count">{m.experts.map((e) => e.name).join(", ")}</span>}
            </button>
          ))}
        </div>
        <button className="link" onClick={() => { write(CODE_KEY, null); setCode(null); setMeetings(null); }}>
          Logg ut
        </button>
      </div>
    );
  }
  return <MeetingView key={`${review ? REVIEW : ""}${meeting.id}`} code={code} meeting={meeting} index={index}
                      queue={queue} status={status} review={review} onLeave={() => pickMeeting(null)} />;
}

function Login({ error, onCode, retry }: { error: string | null; onCode: (c: string) => void; retry?: () => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="center-screen">
      <h1>Konsensusmøte</h1>
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
