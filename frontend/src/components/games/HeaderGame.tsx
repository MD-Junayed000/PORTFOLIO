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

const ENEMY_COLORS = ["#47d147", "#68a063", "#dc382c", "#777bb3"];
const ENEMY_LABELS = ["Nginx", "Node", "Redis", "PHP"];
const GRAVITY = 0.6;
const JUMP_FORCE = -10;
const GROUND_OFFSET = 30;
const GAME_SPEED = 3;

export default function HeaderGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const playerRef = useRef<Entity>({ x: 40, y: 0, vy: 0, width: 20, height: 20 });
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
    playerRef.current = { x: 40, y: ground - 20, vy: 0, width: 20, height: 20 };
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

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resizeCanvas = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = 80;
      }
    };
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    const ground = canvas.height - GROUND_OFFSET;
    playerRef.current.y = ground - 20;

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
        if (frameRef.current % 90 === 0) {
          const idx = Math.floor(Math.random() * ENEMY_LABELS.length);
          obstaclesRef.current.push({
            x: width,
            y: groundY - 18,
            width: 18,
            height: 18,
            color: ENEMY_COLORS[idx],
            label: ENEMY_LABELS[idx],
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

        // Draw player (sparkle/asterisk shape)
        ctx.fillStyle = "#d97706";
        const px = player.x + player.width / 2;
        const py = player.y + player.height / 2;
        ctx.beginPath();
        for (let i = 0; i < 8; i++) {
          const angle = (i * Math.PI) / 4;
          const r = i % 2 === 0 ? 10 : 5;
          const sx = px + Math.cos(angle) * r;
          const sy = py + Math.sin(angle) * r;
          if (i === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        }
        ctx.closePath();
        ctx.fill();

        // Draw obstacles
        for (const obs of obstaclesRef.current) {
          ctx.fillStyle = obs.color;
          ctx.fillRect(obs.x, obs.y, obs.width, obs.height);
          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 7px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(obs.label[0], obs.x + obs.width / 2, obs.y + obs.height / 2 + 3);
        }
      } else {
        // Game over state
        ctx.fillStyle = "#6b7280";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Game Over! Click to restart", width / 2, height / 2);
      }

      // Draw score
      ctx.fillStyle = "#6b7280";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`Score: ${Math.floor(scoreRef.current / 10)}`, width - 10, 14);

      animRef.current = requestAnimationFrame(gameLoop);
    };

    animRef.current = requestAnimationFrame(gameLoop);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resizeCanvas);
    };
  }, []);

  return (
    <div className="w-full h-20 relative cursor-pointer select-none" onClick={jump} onKeyDown={(e) => e.key === " " && jump()} tabIndex={0}>
      <canvas ref={canvasRef} className="w-full h-full block" />
      {!gameOver && score === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <span className="text-xs text-muted/60">Click to jump!</span>
        </div>
      )}
    </div>
  );
}
