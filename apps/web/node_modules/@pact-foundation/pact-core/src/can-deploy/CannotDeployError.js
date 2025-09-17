"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CannotDeployError = void 0;
class CannotDeployError extends Error {
    constructor(output) {
        super('can-i-deploy result: it is not safe to deploy');
        this.name = 'CannotDeployError';
        this.output = output;
    }
}
exports.CannotDeployError = CannotDeployError;
//# sourceMappingURL=CannotDeployError.js.map