import { MessageOptions } from './types';
export declare class Message {
    readonly options: MessageOptions;
    private readonly __argMapping;
    constructor(passedOptions?: MessageOptions);
    createMessage(): Promise<unknown>;
}
declare const _default: (options: MessageOptions) => Message;
export default _default;
