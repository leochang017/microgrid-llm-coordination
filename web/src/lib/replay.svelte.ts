/**
 * Shared replay UI state for one `/run/[cell]/` page: which tick is showing, whether
 * playback is running, and which optional overlays are on. One instance per page,
 * passed by reference into `NeighborhoodGrid` / `TickScrubber` (and, in later tasks,
 * `MessagePanel` / `HousePanel`) so every panel reads and writes the same tick.
 */
export class ReplayState {
	tick = $state(0);
	playing = $state(false);
	speed = $state<1 | 2 | 4>(1);
	selectedHouse = $state<string | null>(null);

	// Overlay toggles. Grid-only for now (Task 5); Task 6 wires showTransfers/showCircles
	// into NeighborhoodGrid, Task 7 wires showMessages into the message overlay + panel.
	showTransfers = $state(true);
	showMessages = $state(false);
	showCircles = $state(false);

	/** Every tick change should go through this so it can never land outside [0, max]. */
	seek(t: number, max: number): void {
		this.tick = Math.min(max, Math.max(0, t));
	}

	togglePlay(): void {
		this.playing = !this.playing;
	}
}
