import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DeclarationComponent } from './declaration/declaration.component';
import { PreprocessingComponent } from './preprocessing/preprocessing.component';
import { ModelingComponent } from './modeling/modeling.component';
import { EvaluationComponent } from './evaluation/evaluation.component';
import { DeploymentComponent } from './deployment/deployment.component';
import { ModelDevelopmentComponent } from './model-development/model-development.component';
import { HomeComponent } from './home/home.component';
import { LoginComponent } from './login/login.component';
import { FeatureStoreComponent } from './feature-store/feature-store.component';
import { UnsavedChangesGuard } from './guards/unsaved-changes.guard';

const routes: Routes = [
  { path: '', redirectTo: '/login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { path: 'home', component: HomeComponent },
  { path: 'feature-store', component: FeatureStoreComponent },
  { path: 'feature-store/projects', component: FeatureStoreComponent, data: { tab: 'projects' } },
  { path: 'feature-store/connections', component: FeatureStoreComponent, data: { tab: 'connections' } },
  { path: 'feature-store/collections', component: FeatureStoreComponent, data: { tab: 'collections' } },
  {
    path: 'model-development',
    component: ModelDevelopmentComponent,
    canDeactivate: [UnsavedChangesGuard],
    children: [
      { path: 'declaration', component: DeclarationComponent },
      { path: 'preprocessing', component: PreprocessingComponent },
      { path: 'modeling', component: ModelingComponent },
      { path: 'evaluation', component: EvaluationComponent },
      { path: 'deployment', component: DeploymentComponent },
      { path: '', redirectTo: 'declaration', pathMatch: 'full' }
    ]
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }