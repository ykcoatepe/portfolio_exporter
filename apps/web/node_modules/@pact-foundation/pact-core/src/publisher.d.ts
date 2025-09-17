import { PublisherOptions } from './types';
export declare class Publisher {
    readonly options: PublisherOptions;
    private readonly __argMapping;
    constructor(passedOptions: PublisherOptions);
    publish(): Promise<string[]>;
}
declare const _default: (options: PublisherOptions) => Publisher;
export default _default;
