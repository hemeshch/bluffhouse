import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { SetupForm } from "./SetupForm";
import { LiveBoard } from "./LiveBoard";
import { useLiveGame, type LiveStartRequest } from "./useLiveGame";
import "./Live.css";
import "../replay/Replay.css";

export function LivePage() {
  const game = useLiveGame();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [params] = useSearchParams();
  const autostarted = useRef(false);

  // /live?demo=bots — instantly deal a keyless bots game (handy when demoing)
  useEffect(() => {
    if (params.get("demo") === "bots" && !autostarted.current) {
      autostarted.current = true;
      void onStart({
        seats: ["random", "checkcall", "allin", "fold"].map((b) => ({ spec: b })),
        hands: 6,
        mode: 0,
        seed: null,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const onStart = async (req: LiveStartRequest) => {
    setStarting(true);
    setStartError(null);
    try {
      await game.start(req);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  if (!game.config) {
    return (
      <div className="live-page">
        <SetupForm busy={starting} onStart={onStart} />
        {startError && <p className="live-error mono">{startError}</p>}
      </div>
    );
  }

  return (
    <div className="live-page running">
      {game.error && <p className="live-error mono">{game.error}</p>}
      <LiveBoard
        config={game.config}
        events={game.events}
        activity={game.activity}
        done={game.done}
        onStop={game.stop}
        onReset={game.reset}
      />
    </div>
  );
}
