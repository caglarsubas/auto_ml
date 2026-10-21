import { fakeAsync, tick } from '@angular/core/testing';
import { downloadBlob } from './download-blob';

describe('Browser download dispatch', () => {
  it('keeps an attached, exact-filename URL valid until asynchronous dispatch', fakeAsync(() => {
    spyOn(URL, 'createObjectURL').and.returnValue('blob:owned');
    const revoke = spyOn(URL, 'revokeObjectURL');
    const click = spyOn(HTMLAnchorElement.prototype, 'click').and.callFake(function (
      this: HTMLAnchorElement,
    ) {
      expect(this.isConnected).toBeTrue();
      expect(this.href).toBe('blob:owned');
      expect(this.download).toBe('evidence.json');
      expect(revoke).not.toHaveBeenCalled();
    });
    downloadBlob(new Blob(['evidence']), 'evidence.json');
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[download="evidence.json"]')).toBeNull();
    tick(999);
    expect(revoke).not.toHaveBeenCalled();
    tick(1);
    expect(revoke).toHaveBeenCalledOnceWith('blob:owned');
  }));
  it('cleans up once even when browser dispatch throws', fakeAsync(() => {
    spyOn(URL, 'createObjectURL').and.returnValue('blob:owned');
    const revoke = spyOn(URL, 'revokeObjectURL');
    spyOn(HTMLAnchorElement.prototype, 'click').and.throwError('synthetic dispatch failure');
    expect(() => downloadBlob(new Blob(['evidence']), 'failed.json')).toThrowError(
      'synthetic dispatch failure',
    );
    expect(document.querySelector('a[download="failed.json"]')).toBeNull();
    expect(revoke).not.toHaveBeenCalled();
    tick(1000);
    expect(revoke).toHaveBeenCalledOnceWith('blob:owned');
  }));
});
