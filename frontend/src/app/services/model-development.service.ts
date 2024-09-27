// model-development.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ModelDevelopmentService {
  private isStartedSubject = new BehaviorSubject<boolean>(false);
  isStarted$ = this.isStartedSubject.asObservable();

  constructor() {
    console.log('ModelDevelopmentService: Initialized');
  }

  setIsStarted(value: boolean) {
    console.log('ModelDevelopmentService: Setting isStarted to', value);
    this.isStartedSubject.next(value);
  }
}