"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getBinaryEntry = exports.createConfig = exports.PACT_STANDALONE_VERSION = void 0;
const chalk = require("chalk");
exports.PACT_STANDALONE_VERSION = '2.0.2';
function makeError(msg) {
    return new Error(chalk.red(`Error while locating pact binary: ${msg}`));
}
function createConfig() {
    return {
        binaries: [
            ['win32', 'x86', 'windows', 'x86', 'zip'],
            ['win32', 'x64', 'windows', 'x86_64', 'zip'],
            ['darwin', 'arm64', 'osx', 'arm64', 'tar.gz'],
            ['darwin', 'x64', 'osx', 'x86_64', 'tar.gz'],
            ['linux', 'arm64', 'linux', 'arm64', 'tar.gz'],
            ['linux', 'x64', 'linux', 'x64', 'tar.gz'],
        ].map(([platform, arch, downloadPlatform, downloadArch, extension]) => {
            const binary = `pact-${exports.PACT_STANDALONE_VERSION}-${downloadPlatform}-${downloadArch}.${extension}`;
            return {
                platform,
                arch,
                binary,
                binaryChecksum: `${binary}.checksum`,
                folderName: `${platform}-${arch}-${exports.PACT_STANDALONE_VERSION}`,
            };
        }),
    };
}
exports.createConfig = createConfig;
const CONFIG = createConfig();
function getBinaryEntry(platform = process.platform, arch = process.arch) {
    const found = CONFIG.binaries.find((value) => value.platform === platform && (value.arch ? value.arch === arch : true));
    if (found === undefined) {
        throw makeError(`Cannot find binary for platform '${platform}' with architecture '${arch}'.`);
    }
    return found;
}
exports.getBinaryEntry = getBinaryEntry;
//# sourceMappingURL=install.js.map