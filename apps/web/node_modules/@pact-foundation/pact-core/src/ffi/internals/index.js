"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.libName = void 0;
const PLATFORM_LOOKUP = {
    linux: 'linux',
    darwin: 'osx',
    win32: 'windows',
};
const LIBNAME_PREFIX_LOOKUP = {
    linux: 'lib',
    darwin: 'lib',
    win32: '',
};
const ARCH_LOOKUP = { x64: 'x86_64', arm64: 'aarch64' };
const EXTENSION_LOOKUP = {
    'osx-x86_64': 'dylib',
    'osx-aarch64': 'dylib',
    'linux-x86_64': 'so',
    'linux-aarch64': 'so',
    'windows-x86_64': 'dll',
};
const libName = (library, version, processArch = process.arch, processPlatform = process.platform) => {
    const arch = ARCH_LOOKUP[processArch];
    const platform = PLATFORM_LOOKUP[processPlatform];
    if (!arch || !platform) {
        throw new Error(`Pact does not currently support the operating system and architecture combination '${processPlatform}/${processArch}'`);
    }
    const target = `${platform}-${arch}`;
    const extension = EXTENSION_LOOKUP[target];
    if (!extension) {
        throw new Error(`Pact doesn't know what extension to use for the libraries in the architecture combination '${target}'`);
    }
    const libnamePrefix = LIBNAME_PREFIX_LOOKUP[processPlatform];
    if (libnamePrefix === undefined) {
        throw new Error(`Pact doesn't know what prefix to use for the libraries on '${processPlatform}'`);
    }
    return `${version}-${libnamePrefix}${library}-${target}.${extension}`;
};
exports.libName = libName;
//# sourceMappingURL=index.js.map