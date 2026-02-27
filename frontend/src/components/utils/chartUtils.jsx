// src/utils/chartUtils.js

export function getNiceStep(maxValue, tickCount) {
  if (maxValue <= 0) return 1;

  const roughStep = maxValue / tickCount;
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const residual = roughStep / magnitude;

  let niceResidual;
  if (residual >= 5) niceResidual = 5;
  else if (residual >= 2) niceResidual = 2;
  else niceResidual = 1;

  return niceResidual * magnitude;
}