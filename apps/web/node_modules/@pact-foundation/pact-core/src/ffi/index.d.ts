import { LogLevel } from '../logger/types';
import { Ffi } from './types';
declare const ffiLib: Ffi;
export declare const PACT_FFI_VERSION = "0.4.0";
declare let ffi: typeof ffiLib;
export declare const getFfiLib: (logLevel?: LogLevel) => typeof ffi;
export {};
