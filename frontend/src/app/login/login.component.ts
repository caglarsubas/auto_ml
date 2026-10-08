// login.component.ts
import {
  Component,
  OnInit,
  OnDestroy,
  Inject,
  PLATFORM_ID,
  ChangeDetectionStrategy,
} from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { isPlatformBrowser } from '@angular/common';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
  changeDetection: ChangeDetectionStrategy.Eager,
  standalone: false,
})
export class LoginComponent implements OnInit, OnDestroy {
  username: string = '';
  password: string = '';
  errorMessage: string = '';
  signingIn: boolean = false;
  isBrowser: boolean;

  constructor(
    private router: Router,
    private authService: AuthService,
    @Inject(PLATFORM_ID) private platformId: object,
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);
  }

  ngOnInit() {
    if (this.isBrowser) {
      document.body.classList.add('login-page');
    }
  }

  ngOnDestroy() {
    if (this.isBrowser) {
      document.body.classList.remove('login-page');
    }
  }

  onSubmit() {
    if (this.signingIn) return;
    this.signingIn = true;
    this.errorMessage = '';
    this.authService.login(this.username, this.password).subscribe(valid => {
      this.signingIn = false;
      this.password = '';
      if (valid) this.router.navigate(['/home']);
      else this.errorMessage = 'Sign-in failed. Check your credentials and connection.';
    });
  }
}
