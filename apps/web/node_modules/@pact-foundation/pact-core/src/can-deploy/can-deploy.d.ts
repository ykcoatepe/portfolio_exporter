import { CanDeployOptions, CanDeployResponse } from './types';
export declare class CanDeploy {
    static convertForSpawnBinary(options: CanDeployOptions): CanDeployOptions[];
    readonly options: CanDeployOptions;
    private readonly __argMapping;
    constructor(passedOptions: CanDeployOptions);
    canDeploy(): Promise<CanDeployResponse | string>;
}
declare const _default: (options: CanDeployOptions) => CanDeploy;
export default _default;
