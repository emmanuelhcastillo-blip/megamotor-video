import React from 'react';
import {Composition} from 'remotion';
import {Grafico, GraficoProps} from './Grafico';

const FPS = 30;

const defaults: GraficoProps = {
  kind: 'titular',
  text: 'Titular de prueba',
  seconds: 2.5,
};

export const Root: React.FC = () => (
  <Composition
    id="Grafico"
    component={Grafico}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={Math.round(defaults.seconds * FPS)}
    defaultProps={defaults}
    calculateMetadata={({props}) => ({durationInFrames: Math.max(1, Math.round(props.seconds * FPS))})}
  />
);
