import { AbstractService } from './service';
import { LogLevel } from './logger/types';
export declare class Stub extends AbstractService {
    readonly options: StubOptions;
    constructor(passedOptions?: StubOptions);
}
declare const _default: (options?: StubOptions) => Stub;
export default _default;
export interface StubOptions {
    pactUrls?: string[];
    port?: number;
    ssl?: boolean;
    cors?: boolean;
    host?: string;
    sslcert?: string;
    sslkey?: string;
    log?: string;
    logLevel?: LogLevel;
    timeout?: number;
}
