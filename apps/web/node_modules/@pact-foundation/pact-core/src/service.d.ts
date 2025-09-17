/// <reference types="node" />
/// <reference types="node" />
import events = require('events');
import { ChildProcess } from 'child_process';
import { CliVerbOptions } from './spawn';
import { ServiceOptions } from './types';
interface AbstractServiceEventInterface {
    START_EVENT: string;
    STOP_EVENT: string;
    DELETE_EVENT: string;
}
export declare abstract class AbstractService extends events.EventEmitter {
    static get Events(): AbstractServiceEventInterface;
    readonly options: ServiceOptions;
    protected __argMapping: Record<string, string>;
    protected __running: boolean;
    protected __instance: ChildProcess | undefined;
    protected __cliVerb?: CliVerbOptions;
    protected __serviceCommand: string;
    protected constructor(command: string, options: ServiceOptions, argMapping: Record<string, string>, cliVerb?: CliVerbOptions);
    start(): Promise<AbstractService>;
    stop(): Promise<AbstractService>;
    delete(): Promise<AbstractService>;
    protected spawnBinary(): ChildProcess;
    protected __waitForServiceUp(): Promise<unknown>;
    protected __waitForServiceDown(): Promise<unknown>;
    private __call;
}
export {};
