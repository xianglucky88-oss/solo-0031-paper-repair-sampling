import {choice, field, number} from './fields.js';

export const stockFields = [number('thickness', '厚度 μm'), number('ph', 'pH × 10'),
  choice('grain', '纤维轴', [['x', '横向 x'], ['y', '纵向 y']])];
export const stock = ({thickness, ph, grain}) => ({thickness, ph, grain});

export function surfaceFields(key, label) {
  return [field(`${key}Condition`, `${label}测量条件`, 'D50'), number(`${key}L`, `${label} L* × 10`),
    number(`${key}A`, `${label} a* × 10`), number(`${key}B`, `${label} b* × 10`)];
}

export function surface(values, key) {
  return {condition: values[`${key}Condition`], lab: {l: values[`${key}L`], a: values[`${key}A`], b: values[`${key}B`]}};
}
