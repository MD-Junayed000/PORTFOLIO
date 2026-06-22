"use client";

import { useRef, useEffect, useState, useCallback } from "react";

interface Entity {
  x: number;
  y: number;
  vy: number;
  width: number;
  height: number;
}

interface Obstacle {
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  label: string;
}

const ENEMY_CONFIGS = [
  { label: "nginx", color: "#009639" },
  { label: "PHP", color: "#777BB4" },
  { label: "Redis", color: "#DC382D" },
  { label: "Kafka", color: "#231F20" },
  { label: "GPT", color: "#10A37F" },
  { label: "Gemini", color: "#4285F4" },
  { label: "AWS", color: "#FF9900" },
  { label: "Docker", color: "#2496ED" },
  { label: "Node", color: "#68A063" },
  { label: "Go", color: "#00ADD8" },
];

const GRAVITY = 0.55;
const JUMP_FORCE = -10.5;
const GROUND_OFFSET = 30;
const GAME_SPEED = 3;

export default function HeaderGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const playerRef = useRef<Entity>({ x: 40, y: 0, vy: 0, width: 30, height: 30 });
  const obstaclesRef = useRef<Obstacle[]>([]);
  const frameRef = useRef(0);
  const scoreRef = useRef(0);
  const gameOverRef = useRef(false);
  const [score, setScore] = useState(0);
  const [gameOver, setGameOver] = useState(false);

  const resetGame = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ground = canvas.height - GROUND_OFFSET;
    playerRef.current = { x: 40, y: ground - 30, vy: 0, width: 30, height: 30 };
    obstaclesRef.current = [];
    frameRef.current = 0;
    scoreRef.current = 0;
    gameOverRef.current = false;
    setScore(0);
    setGameOver(false);
  }, []);

  const jump = useCallback(() => {
    if (gameOverRef.current) {
      resetGame();
      return;
    }
    const player = playerRef.current;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ground = canvas.height - GROUND_OFFSET;
    if (player.y >= ground - player.height - 1) {
      player.vy = JUMP_FORCE;
    }
  }, [resetGame]);

  // Keyboard event listener for spacebar - scoped to game container focus
  useEffect(() => {
    const container = canvasRef.current?.parentElement;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" || e.key === " ") {
        // Only handle space when the game container (or its children) is focused
        if (container && container.contains(document.activeElement as Node)) {
          e.preventDefault();
          jump();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [jump]);

  // Touch event listener for mobile
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const handleTouch = (e: TouchEvent) => {
      e.preventDefault();
      jump();
    };
    canvas.addEventListener("touchstart", handleTouch, { passive: false });
    return () => canvas.removeEventListener("touchstart", handleTouch);
  }, [jump]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resizeCanvas = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = 120;
      }
    };
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    const ground = canvas.height - GROUND_OFFSET;
    playerRef.current.y = ground - 30;

    const drawPlayer = (ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number) => {
      // Claude logo-inspired player: recognizable orange circle/face with subtle smile
      const cx = x + width / 2;
      const cy = y + height / 2;
      const radius = width / 2;

      // Outer circle - warm orange/coral
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = "#E8733A";
      ctx.fill();

      // Inner lighter circle for depth
      ctx.beginPath();
      ctx.arc(cx, cy, radius * 0.82, 0, Math.PI * 2);
      ctx.fillStyle = "#F29B68";
      ctx.fill();

      // Core warm highlight
      ctx.beginPath();
      ctx.arc(cx, cy - radius * 0.1, radius * 0.55, 0, Math.PI * 2);
      ctx.fillStyle = "#F4B887";
      ctx.fill();

      // Eyes - two small dark dots
      ctx.fillStyle = "#5C3317";
      ctx.beginPath();
      ctx.arc(cx - radius * 0.25, cy - radius * 0.15, radius * 0.09, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx + radius * 0.25, cy - radius * 0.15, radius * 0.09, 0, Math.PI * 2);
      ctx.fill();

      // Subtle smile - a gentle arc
      ctx.beginPath();
      ctx.arc(cx, cy + radius * 0.05, radius * 0.3, 0.15 * Math.PI, 0.85 * Math.PI, false);
      ctx.strokeStyle = "#5C3317";
      ctx.lineWidth = 1.5;
      ctx.lineCap = "round";
      ctx.stroke();
    };

    const drawEnemy = (ctx: CanvasRenderingContext2D, obs: Obstacle) => {
      // Rounded rectangle with brand color
      const r = 3;
      ctx.beginPath();
      ctx.moveTo(obs.x + r, obs.y);
      ctx.lineTo(obs.x + obs.width - r, obs.y);
      ctx.quadraticCurveTo(obs.x + obs.width, obs.y, obs.x + obs.width, obs.y + r);
      ctx.lineTo(obs.x + obs.width, obs.y + obs.height - r);
      ctx.quadraticCurveTo(obs.x + obs.width, obs.y + obs.height, obs.x + obs.width - r, obs.y + obs.height);
      ctx.lineTo(obs.x + r, obs.y + obs.height);
      ctx.quadraticCurveTo(obs.x, obs.y + obs.height, obs.x, obs.y + obs.height - r);
      ctx.lineTo(obs.x, obs.y + r);
      ctx.quadraticCurveTo(obs.x, obs.y, obs.x + r, obs.y);
      ctx.closePath();
      ctx.fillStyle = obs.color;
      ctx.fill();

      // Label text
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 6px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(obs.label, obs.x + obs.width / 2, obs.y + obs.height / 2);
    };

    const gameLoop = () => {
      if (!canvas || !ctx) return;
      const { width, height } = canvas;
      const groundY = height - GROUND_OFFSET;

      ctx.clearRect(0, 0, width, height);

      // Draw ground line
      ctx.strokeStyle = "#e5e2dc";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, groundY);
      ctx.lineTo(width, groundY);
      ctx.stroke();

      if (!gameOverRef.current) {
        // Update player
        const player = playerRef.current;
        player.vy += GRAVITY;
        player.y += player.vy;
        if (player.y >= groundY - player.height) {
          player.y = groundY - player.height;
          player.vy = 0;
        }

        // Spawn obstacles
        frameRef.current++;
        if (frameRef.current % 85 === 0) {
          const idx = Math.floor(Math.random() * ENEMY_CONFIGS.length);
          const config = ENEMY_CONFIGS[idx];
          const labelWidth = Math.max(config.label.length * 5 + 8, 22);
          obstaclesRef.current.push({
            x: width,
            y: groundY - 18,
            width: labelWidth,
            height: 18,
            color: config.color,
            label: config.label,
          });
        }

        // Update obstacles
        obstaclesRef.current = obstaclesRef.current.filter((o) => o.x + o.width > 0);
        for (const obs of obstaclesRef.current) {
          obs.x -= GAME_SPEED;
        }

        // Check collisions
        for (const obs of obstaclesRef.current) {
          if (
            player.x < obs.x + obs.width &&
            player.x + player.width > obs.x &&
            player.y < obs.y + obs.height &&
            player.y + player.height > obs.y
          ) {
            gameOverRef.current = true;
            setGameOver(true);
            break;
          }
        }

        // Update score
        if (!gameOverRef.current) {
          scoreRef.current++;
          if (scoreRef.current % 10 === 0) {
            setScore(Math.floor(scoreRef.current / 10));
          }
        }

        // Draw player (Claude-inspired icon)
        drawPlayer(ctx, player.x, player.y, player.width, player.height);

        // Draw obstacles (tech brand enemies)
        for (const obs of obstaclesRef.current) {
          drawEnemy(ctx, obs);
        }
      } else {
        // Game over state
        ctx.fillStyle = "#6b7280";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("Game Over! Click or press Space to restart", width / 2, height / 2);
      }

      // Draw score
      ctx.fillStyle = "#6b7280";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "top";
      ctx.fillText(`Score: ${Math.floor(scoreRef.current / 10)}`, width - 10, 4);

      animRef.current = requestAnimationFrame(gameLoop);
    };

    animRef.current = requestAnimationFrame(gameLoop);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resizeCanvas);
    };
  }, []);

  return (
    <div
      className="w-full h-[120px] relative cursor-pointer select-none outline-none"
      onClick={jump}
      tabIndex={0}
      role="button"
      aria-label="Jump game - click or press spacebar to jump"
    >
      <canvas ref={canvasRef} className="w-full h-full block" />
      {!gameOver && score === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="text-xs text-muted/60">Click or press Space to jump!</span>
        </div>
      )}
    </div>
  );
}
