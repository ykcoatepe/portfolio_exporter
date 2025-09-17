export declare const PACT_STANDALONE_VERSION = "2.0.2";
export declare function createConfig(): Config;
export declare function getBinaryEntry(platform?: string, arch?: string): BinaryEntry;
export interface Config {
    binaries: BinaryEntry[];
}
export interface BinaryEntry {
    platform: string;
    arch?: string;
    binary: string;
    binaryChecksum: string;
    folderName: string;
}
