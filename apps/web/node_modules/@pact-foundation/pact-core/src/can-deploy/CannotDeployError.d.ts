import { CanDeployResponse } from './types';
export declare class CannotDeployError extends Error {
    output: CanDeployResponse | string;
    constructor(output: CanDeployResponse | string);
}
