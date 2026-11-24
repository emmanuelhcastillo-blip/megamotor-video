import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

// Colores y letra en línea con los subtítulos del motor (amarillo ES, contorno negro).
const ACCENT = '#FFE500';
const FONT = 'Inter, "DejaVu Sans", sans-serif';
const SHADOW = '0 6px 24px rgba(0,0,0,.55)';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const OUT = Easing.bezier(0.16, 1, 0.3, 1);

export type Palabra = {w: string; t: number};
export type GraficoProps = {
  kind: 'titular' | 'cifra' | 'cinetica' | 'barrido';
  seconds: number;
  text?: string;
  value?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  label?: string;
  words?: Palabra[];
  position?: 'arriba' | 'centro';
  top?: number; // px desde arriba; lo decide el motor para no tapar la cara
};

// Zona segura: los subtítulos ES ocupan ~300-420 px arriba, el PT y la interfaz de Instagram abajo.
const top = (p?: string, px?: number) => px ?? (p === 'centro' ? 760 : 520);

const useInOut = (inFrames = 9, outFrames = 7) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const enter = interpolate(frame, [0, inFrames], [0, 1], {...clamp, easing: OUT});
  const exit = interpolate(frame, [durationInFrames - outFrames, durationInFrames], [1, 0], clamp);
  return {frame, enter, exit};
};

const Titular: React.FC<GraficoProps> = ({text = '', position, top: props_top}) => {
  const {enter, exit} = useInOut();
  return (
    <AbsoluteFill style={{alignItems: 'center'}}>
      <div
        style={{
          position: 'absolute',
          top: top(position, props_top),
          maxWidth: 920,
          padding: '26px 40px',
          background: ACCENT,
          color: '#111',
          fontFamily: FONT,
          fontWeight: 900,
          fontSize: 78,
          lineHeight: 1.05,
          textAlign: 'center',
          textTransform: 'uppercase',
          letterSpacing: -1,
          boxShadow: SHADOW,
          opacity: exit,
          translate: `0px ${(1 - enter) * 60}px`,
          clipPath: `inset(0 ${(1 - enter) * 100}% 0 0)`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

const Cifra: React.FC<GraficoProps> = ({value = 0, decimals = 0, prefix = '', suffix = '', label = '', position, top: props_top}) => {
  const {frame, enter, exit} = useInOut();
  const {fps} = useVideoConfig();
  const n = interpolate(frame, [0, Math.round(1.1 * fps)], [0, value], {...clamp, easing: OUT});
  const shown = n.toLocaleString('es-ES', {minimumFractionDigits: decimals, maximumFractionDigits: decimals});
  return (
    <AbsoluteFill style={{alignItems: 'center'}}>
      <div style={{position: 'absolute', top: top(position, props_top), textAlign: 'center', opacity: exit, fontFamily: FONT}}>
        <div
          style={{
            color: ACCENT,
            fontWeight: 900,
            fontSize: 190,
            lineHeight: 1,
            WebkitTextStroke: '6px #000',
            paintOrder: 'stroke fill',
            textShadow: SHADOW,
            scale: interpolate(enter, [0, 1], [0.6, 1]),
          }}
        >
          {prefix}
          {shown}
          {suffix}
        </div>
        {label ? (
          <div
            style={{
              marginTop: 18,
              color: '#fff',
              fontWeight: 800,
              fontSize: 54,
              textTransform: 'uppercase',
              WebkitTextStroke: '3px #000',
              paintOrder: 'stroke fill',
              opacity: interpolate(frame, [6, 16], [0, 1], clamp),
            }}
          >
            {label}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

// Tipografía cinética: cada palabra entra en el instante en que se dice (t relativo al inicio del gráfico).
const Cinetica: React.FC<GraficoProps> = ({words = [], text = '', position, top: props_top}) => {
  const {frame, exit} = useInOut();
  const {fps, durationInFrames} = useVideoConfig();
  const list: Palabra[] = words.length
    ? words
    : text.split(/\s+/).filter(Boolean).map((w, i, a) => ({w, t: (i * (durationInFrames / fps) * 0.7) / a.length}));
  return (
    <AbsoluteFill style={{alignItems: 'center'}}>
      <div
        style={{
          position: 'absolute',
          top: top(position, props_top),
          width: 940,
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '6px 22px',
          opacity: exit,
          fontFamily: FONT,
          fontWeight: 900,
          fontSize: 96,
          lineHeight: 1.05,
          textTransform: 'uppercase',
        }}
      >
        {list.map((p, i) => {
          const f0 = Math.round(p.t * fps);
          const on = interpolate(frame, [f0, f0 + 6], [0, 1], {...clamp, easing: OUT});
          const last = i === list.length - 1;
          return (
            <span
              key={i}
              style={{
                color: last ? ACCENT : '#fff',
                WebkitTextStroke: '5px #000',
                paintOrder: 'stroke fill',
                textShadow: SHADOW,
                opacity: on,
                scale: interpolate(on, [0, 1], [1.5, 1]),
                translate: `0px ${(1 - on) * 30}px`,
              }}
            >
              {p.w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// Transición: un panel cruza la pantalla y la deja limpia; cubre el corte en su punto medio.
const Barrido: React.FC<GraficoProps> = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const x = interpolate(frame, [0, durationInFrames], [-110, 110], {...clamp, easing: Easing.inOut(Easing.cubic)});
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: ACCENT, transform: `translateX(${x}%) skewX(-12deg) scale(1.3)`}} />
      <AbsoluteFill style={{background: '#111', transform: `translateX(${x - 18}%) skewX(-12deg) scale(1.3)`, opacity: 0.9}} />
    </AbsoluteFill>
  );
};

export const Grafico: React.FC<GraficoProps> = (p) => {
  if (p.kind === 'cifra') return <Cifra {...p} />;
  if (p.kind === 'cinetica') return <Cinetica {...p} />;
  if (p.kind === 'barrido') return <Barrido {...p} />;
  return <Titular {...p} />;
};
