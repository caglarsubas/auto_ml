// auth.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private isLoggedInSubject = new BehaviorSubject<boolean>(false);
  isLoggedIn$ = this.isLoggedInSubject.asObservable();

  login(username: string, password: string): boolean {
    if (username === 'caglarsubas@gmail.com' && password === 'con3e7ne') {
      this.isLoggedInSubject.next(true);
      return true;
    }
    return false;
  }

  logout() {
    this.isLoggedInSubject.next(false);
    // You can add any additional logout logic here, such as clearing local storage
  }
}