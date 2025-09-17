import { VerifierOptions } from '../verifier/types';
import { MessageOptions, PublisherOptions, ServiceOptions } from '../types';
import { CanDeployOptions } from '../can-deploy/types';
export declare type CliVerbOptions = {
    cliVerb: string;
};
export declare type SpawnArgument = CanDeployOptions | MessageOptions | PublisherOptions | ServiceOptions | VerifierOptions | CliVerbOptions | {};
export declare type SpawnArguments = Array<SpawnArgument> | SpawnArgument;
export declare const DEFAULT_ARG = "DEFAULT";
export declare const PACT_NODE_NO_VALUE = "PACT_NODE_NO_VALUE";
export declare class Arguments {
    toArgumentsArray(args: SpawnArguments, mappings: {
        [id: string]: string;
    }): string[];
    private createArgumentsFromObject;
}
declare const _default: Arguments;
export default _default;
